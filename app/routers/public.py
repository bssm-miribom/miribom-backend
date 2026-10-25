"""시민 화면 API (C1 장소 검색, C2 3일 혼잡). 로그인 없음, 관리자 지표는 안 내보냄"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import views
from app.db import Alias, Place, get_session
from app.routers.admin import active_notices

router = APIRouter(tags=["public"])


@router.get("/places/search")
def search(q: str = "", s: Session = Depends(get_session)):
    q = q.strip()
    row = views.find_result(s)
    places = {p.id: p for p in s.scalars(select(Place))}
    hits: dict[str, str | None] = {}
    for p in places.values():
        if not q or q in p.name:
            hits[p.id] = None
    if q:
        for a in s.scalars(select(Alias).where(Alias.alias.contains(q))):
            hits.setdefault(a.place_id, a.alias)
    out = []
    for pid, alias in hits.items():
        p = places[pid]
        days = views.crowd_days(row, p)
        out.append({"id": p.id, "name": p.name, "district": p.district, "matched_alias": alias,
                    "tomorrow": days[0] if days else None})
    return sorted(out, key=lambda x: x["name"])


@router.get("/places/{place_id}/forecast")
def forecast(place_id: str, s: Session = Depends(get_session)):
    p = s.get(Place, place_id)
    if not p:
        raise HTTPException(404, "아직 예보가 없는 장소임")
    row = views.find_result(s)
    days = views.crowd_days(row, p)
    return {"meta": views.meta(row) if row else None,
            "place": {"id": p.id, "name": p.name, "district": p.district},
            "days": days, "least_crowded": views.least_crowded(days),
            "notices": active_notices(s, p.id), "disclaimer": views.DISCLAIMER}


@router.get("/notices")
def notices(s: Session = Depends(get_session)):
    return active_notices(s)
