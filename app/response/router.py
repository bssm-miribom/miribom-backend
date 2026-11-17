"""대응 (A-10~A-12, B-01, B-03)과 실측 회신 (A-14, B-04)"""
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Account
from app.auth.service import can_see, city_account, current_account
from app.core.config import KST
from app.core.db import get_session
from app.dashboard import views
from app.places.models import Place
from app.response import notify
from app.response.models import Checklist, Contact, Notification, Response, VisitorReport

router = APIRouter(prefix="/admin", tags=["대응·회신"])
Level = Literal["none", "stage1", "stage2", "stage3"]


def _place(s: Session, place_id: str, acc: Account) -> Place:
    p = s.get(Place, place_id)
    if not p or not can_see(acc, p):
        raise HTTPException(404, "없는 장소")
    return p


def checklist_out(c: Checklist) -> dict:
    return {"id": c.id, "place_id": c.place_id, "judge_day": str(c.judge_day), "level": c.level, "items": c.items,
            "done": sum(i["done"] for i in c.items), "total": len(c.items)}


# ===== 대응 수준·조치 요청 (A-11) =====
class ResponseIn(BaseModel):
    judge_day: date
    level: Level
    note: str | None = Field(default=None, max_length=500)
    request_to: list[str] = Field(default_factory=list, description="조치 요청할 기관 계정 username")


@router.put("/places/{place_id}/response")
def set_response(place_id: str, body: ResponseIn, acc: Account = Depends(city_account),
                 s: Session = Depends(get_session)):
    """부산시가 대응 수준을 정함. request_to 기관에 알림을 보내고, 1단계 이상이면 점검표를 만듦"""
    p = _place(s, place_id, acc)
    orgs = []
    for u in dict.fromkeys(body.request_to):
        a = s.scalars(select(Account).where(Account.username == u)).first()
        if not a or a.org_type == "city":
            raise HTTPException(400, f"조치 요청할 수 없는 기관: {u}")
        if a.org_type == "police" and p.id not in (a.place_ids or []):   # 경찰은 요청 받은 장소만 봄
            a.place_ids = [*(a.place_ids or []), p.id]
        orgs.append(a)
    r = Response(place_id=p.id, judge_day=body.judge_day, level=body.level, note=body.note,
                 request_to=[a.username for a in orgs], decided_by=acc.username)
    s.add(r)
    cl = None
    if body.level != "none":
        cl = s.scalars(select(Checklist).where(Checklist.place_id == p.id, Checklist.judge_day == body.judge_day)
                       .order_by(Checklist.created_at.desc())).first()
        if cl is None or cl.level != body.level:   # 단계가 바뀌면 새 점검표 (이미 체크한 같은 항목은 이어받음)
            old = {i["id"]: i for i in (cl.items if cl else [])}
            cl = Checklist(place_id=p.id, judge_day=body.judge_day, level=body.level,
                           items=[old.get(i["id"], i) for i in notify.checklist_items(body.level)])
            s.add(cl)
    s.flush()
    sent = []
    if orgs:
        res = views.find_result(s, body.judge_day)
        row = (views.row_for(s, res, p) if res else None) or {"name": p.name, "stage": body.level}
        row = {**row, "stage": body.level if body.level != "none" else row.get("stage", "stage1")}
        sent = notify.notify(s, p, body.judge_day, row, orgs, reason="request")
    s.commit()
    return {"id": r.id, "place_id": p.id, "judge_day": str(r.judge_day), "level": r.level, "note": r.note,
            "decided_by": r.decided_by, "decided_at": r.decided_at.isoformat(),
            "requests": [{"org": n.org, "status": n.status} for n in sent],
            "checklist": checklist_out(cl) if cl else None}


@router.get("/places/{place_id}/response")
def get_response(place_id: str, judge_day: date, acc: Account = Depends(current_account),
                 s: Session = Depends(get_session)):
    p = _place(s, place_id, acc)
    rows = s.scalars(select(Response).where(Response.place_id == p.id, Response.judge_day == judge_day)
                     .order_by(Response.decided_at.desc())).all()
    return [{"id": r.id, "level": r.level, "note": r.note, "request_to": r.request_to, "decided_by": r.decided_by,
             "decided_at": r.decided_at.isoformat()} for r in rows]


# ===== 점검표 (A-10, B-03) =====
@router.get("/checklists")
def list_checklists(place_id: str | None = None, judge_day: date | None = None,
                    acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    q = select(Checklist).order_by(Checklist.judge_day.desc(), Checklist.created_at.desc())
    if place_id:
        q = q.where(Checklist.place_id == place_id)
    if judge_day:
        q = q.where(Checklist.judge_day == judge_day)
    places = {p.id: p for p in s.scalars(select(Place))}
    return [checklist_out(c) for c in s.scalars(q.limit(100)) if can_see(acc, places[c.place_id])]


class ItemIn(BaseModel):
    done: bool


@router.patch("/checklists/{checklist_id}/items/{item_id}")
def check_item(checklist_id: int, item_id: str, body: ItemIn, acc: Account = Depends(current_account),
               s: Session = Depends(get_session)):
    """체크하면 담당 계정과 시각이 남음. 관할 기관·부산시만"""
    c = s.get(Checklist, checklist_id)
    if not c or not can_see(acc, s.get(Place, c.place_id)):
        raise HTTPException(404, "없는 점검표")
    items = [dict(i) for i in c.items]
    it = next((i for i in items if i["id"] == item_id), None)
    if it is None:
        raise HTTPException(404, "없는 항목")
    it.update(done=body.done, by=acc.username if body.done else None,
              at=datetime.now(KST).isoformat() if body.done else None)
    c.items = items   # JSON 칸은 새 리스트를 넣어야 저장됨
    s.commit()
    return checklist_out(c)


# ===== 경보 알림 (A-12, B-01) =====
@router.get("/notifications")
def notifications(judge_day: date | None = None, place_id: str | None = None,
                  acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    q = select(Notification).order_by(Notification.sent_at.desc(), Notification.id.desc())
    if judge_day:
        q = q.where(Notification.judge_day == judge_day)
    if place_id:
        q = q.where(Notification.place_id == place_id)
    return [{"id": n.id, "place_id": n.place_id, "judge_day": str(n.judge_day), "org": n.org, "stage": n.stage,
             "channel": n.channel, "text": n.text, "status": n.status, "reason": n.reason,
             "sent_at": n.sent_at.isoformat()} for n in s.scalars(q.limit(200))]


class ContactIn(BaseModel):
    channel: Literal["sms", "kakao", "email"]
    to: str = Field(min_length=3, max_length=200)


@router.get("/contacts")
def contacts(acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    return [{"org": c.org, "channel": c.channel, "to": c.to} for c in s.scalars(select(Contact).order_by(Contact.org))]


@router.put("/contacts/{org}")
def set_contact(org: str, body: ContactIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    if not s.scalars(select(Account).where(Account.username == org)).first():
        raise HTTPException(404, "없는 기관 계정")
    c = s.get(Contact, org) or Contact(org=org)
    c.channel, c.to = body.channel, body.to
    s.add(c)
    s.commit()
    return {"org": c.org, "channel": c.channel, "to": c.to}


# ===== 실측 회신 (A-14, B-04) =====
class VisitorIn(BaseModel):
    date: date
    visitors: int = Field(ge=0, le=5_000_000)
    source: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


def _visit_out(v: VisitorReport) -> dict:
    return {"id": v.id, "place_id": v.place_id, "date": str(v.date), "visitors": v.visitors, "source": v.source,
            "note": v.note, "org": v.org, "created_at": v.created_at.isoformat() if v.created_at else None}


@router.post("/places/{place_id}/visitors", status_code=201)
def add_visitors(place_id: str, body: VisitorIn, acc: Account = Depends(current_account),
                 s: Session = Depends(get_session)):
    """같은 날짜·기관 재입력은 덮어씀. 재학습 자료로만 쓰고 그날 판정에는 넣지 않음"""
    p = _place(s, place_id, acc)
    if body.date > datetime.now(KST).date():
        raise HTTPException(400, "미래 날짜는 입력할 수 없음")
    v = s.scalars(select(VisitorReport).where(VisitorReport.place_id == p.id, VisitorReport.date == body.date,
                                              VisitorReport.org == acc.username)).first()
    if v is None:
        v = VisitorReport(place_id=p.id, date=body.date, org=acc.username, visitors=body.visitors)
        s.add(v)
    v.visitors, v.source, v.note = body.visitors, body.source, body.note
    s.commit()
    s.refresh(v)
    return _visit_out(v)


@router.get("/places/{place_id}/visitors")
def list_visitors(place_id: str, date_from: date | None = None, date_to: date | None = None,
                  acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    p = _place(s, place_id, acc)
    q = select(VisitorReport).where(VisitorReport.place_id == p.id).order_by(VisitorReport.date)
    if date_from:
        q = q.where(VisitorReport.date >= date_from)
    if date_to:
        q = q.where(VisitorReport.date <= date_to)
    return [_visit_out(v) for v in s.scalars(q)]
