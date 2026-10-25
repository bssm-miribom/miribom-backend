"""관리자 화면 API (A2 대시보드, A3 장소 상세, A4 재현, 별칭, 공지)"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import views
from app.auth import can_see, city_account, city_or_token, current_account
from app.db import Account, Alias, DailyResult, Notice, Place, get_session
from app.jobs import KST, run_daily_job

router = APIRouter(prefix="/admin", tags=["admin"])


def _result_or_404(s, judge_day, replay):
    row = views.find_result(s, judge_day, replay)
    if not row:
        if replay:
            raise HTTPException(404, f"{judge_day} 재현 결과 없음. POST /api/admin/replay 로 먼저 돌릴 것")
        raise HTTPException(404, "아직 판정 결과가 없음. POST /api/admin/run 으로 한 번 돌릴 것")
    return row


@router.get("/dashboard")
def dashboard(judge_day: date | None = None, replay: bool = False,
              acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    if replay and acc.org_type != "city":
        raise HTTPException(403, "과거 사례 재현은 부산시 계정만 볼 수 있음")
    return views.dashboard(s, _result_or_404(s, judge_day, replay), acc)


@router.get("/places")
def places(acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    al: dict[str, list[str]] = {}
    for a in s.scalars(select(Alias)):
        al.setdefault(a.place_id, []).append(a.alias)
    return [{"id": p.id, "name": p.name, "district": p.district, "aliases": al.get(p.id, [])}
            for p in s.scalars(select(Place).order_by(Place.name)) if can_see(acc, p)]


@router.get("/places/{place_id}")
def place_detail(place_id: str, judge_day: date | None = None, replay: bool = False,
                 acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    place = s.get(Place, place_id)
    if not place or not can_see(acc, place):
        raise HTTPException(404, "없는 장소")
    if replay and acc.org_type != "city":
        raise HTTPException(403, "과거 사례 재현은 부산시 계정만 볼 수 있음")
    return views.place_detail(s, _result_or_404(s, judge_day, replay), place)


# ===== 별칭 (A-06) =====
class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=60)
    place_id: str


def _alias_out(a: Alias) -> dict:
    applies = (a.created_at.astimezone(KST) + timedelta(days=1)).date()
    return {"id": a.id, "alias": a.alias, "place_id": a.place_id, "created_at": a.created_at.isoformat(),
            "applies_from": str(applies)}


@router.get("/aliases")
def list_aliases(acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    return [_alias_out(a) for a in s.scalars(select(Alias).order_by(Alias.created_at.desc()))]


@router.post("/aliases", status_code=201)
def add_alias(body: AliasIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    name = body.alias.strip()
    if not s.get(Place, body.place_id):
        raise HTTPException(404, "없는 장소")
    if s.scalars(select(Alias).where(Alias.alias == name)).first() or \
            s.scalars(select(Place).where(Place.name == name)).first():
        raise HTTPException(409, "이미 등록된 별칭")
    a = Alias(alias=name, place_id=body.place_id, created_by=acc.username)
    s.add(a)
    s.commit()
    s.refresh(a)
    return _alias_out(a)


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    a = s.get(Alias, alias_id)
    if not a:
        raise HTTPException(404, "없는 별칭")
    s.delete(a)
    s.commit()


# ===== 판정 실행·재현 (A-07) =====
class ReplayIn(BaseModel):
    judge_day: date
    force: bool = False


async def _run(**kw):
    try:
        return await run_in_threadpool(run_daily_job, **kw)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@router.post("/replay")
async def replay(body: ReplayIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    if body.judge_day > datetime.now(KST).date():
        raise HTTPException(400, "미래 날짜는 재현할 수 없음")
    row = None if body.force else views.find_result(s, body.judge_day, replay=True)
    if row is None:
        row = await _run(judge_day=body.judge_day, replay=True)
    return views.dashboard(s, row, acc)


@router.post("/run")
async def run_now(who: str = Depends(city_or_token), s: Session = Depends(get_session)):
    row = await _run()
    city = s.scalars(select(Account).where(Account.org_type == "city")).first()
    return views.dashboard(s, s.get(DailyResult, row.id), city)


# ===== 공지 (A-13) =====
class NoticeIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1)
    place_id: str | None = None
    ends_at: datetime | None = None


def notice_out(n: Notice) -> dict:
    return {"id": n.id, "title": n.title, "body": n.body, "place_id": n.place_id,
            "created_at": n.created_at.isoformat(), "ends_at": n.ends_at.isoformat() if n.ends_at else None}


def active_notices(s: Session, place_id: str | None = None) -> list[dict]:
    q = select(Notice).where(or_(Notice.ends_at.is_(None), Notice.ends_at > func.now()))
    if place_id:
        q = q.where(or_(Notice.place_id.is_(None), Notice.place_id == place_id))
    return [notice_out(n) for n in s.scalars(q.order_by(Notice.created_at.desc()))]


@router.post("/notices", status_code=201)
def add_notice(body: NoticeIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    if body.place_id and not s.get(Place, body.place_id):
        raise HTTPException(404, "없는 장소")
    n = Notice(**body.model_dump(), created_by=acc.username)
    s.add(n)
    s.commit()
    s.refresh(n)
    return notice_out(n)


@router.delete("/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: int, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    n = s.get(Notice, notice_id)
    if not n:
        raise HTTPException(404, "없는 공지")
    s.delete(n)
    s.commit()
