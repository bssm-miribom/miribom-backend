"""공지 (A-13 등록·내리기·안전 문자 문안, C-05 시민 화면 표시)"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.models import Account
from app.auth.service import city_account
from app.core.db import get_session
from app.dashboard import views
from app.notices.models import Notice
from app.places.models import Place
from app.response.notify import sms_draft

router = APIRouter(tags=["공지"])


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


@router.get("/notices")
def notices(s: Session = Depends(get_session)):
    """지금 보이는 공지 (로그인 없음)"""
    return active_notices(s)


@router.post("/admin/notices", status_code=201)
def add_notice(body: NoticeIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    if body.place_id and not s.get(Place, body.place_id):
        raise HTTPException(404, "없는 장소")
    n = Notice(**body.model_dump(), created_by=acc.username)
    s.add(n)
    s.commit()
    s.refresh(n)
    return notice_out(n)


@router.delete("/admin/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: int, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    n = s.get(Notice, notice_id)
    if not n:
        raise HTTPException(404, "없는 공지")
    s.delete(n)
    s.commit()


@router.get("/admin/notices/sms-draft")
def notice_sms_draft(place_id: str, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    """안전 안내 문자 검토용 문안 (90자 안). 발송은 하지 않음"""
    p = s.get(Place, place_id)
    if not p:
        raise HTTPException(404, "없는 장소")
    row = views.find_result(s)
    return {"place_id": p.id, "text": sms_draft(p, views.row_for(s, row, p) if row else None)}
