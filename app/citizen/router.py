"""시민 화면 API (C1 장소 검색, C2 3일 혼잡, 시간대별 혼잡). 로그인 없음, 관리자 지표는 안 내보냄"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.citizen.timeslots import distance_m, time_slots
from app.dashboard import views
from app.core.db import get_session
from app.places.models import Alias, Place
from app.notices.router import active_notices

router = APIRouter(tags=["시민"])


# 시연용 과거 날짜 보기: replay_day를 주면 그날 07시까지 자료로 다시 돌린 '재현' 결과를 씀 (가짜 값 아님).
# 재현 결과는 부산시가 /api/admin/replay로 미리 만들어 둔 날짜만 있음. meta.replay=true로 화면이 표시함
ReplayDay = Query(None, description="과거 날짜 재현 결과로 보기 (예: 2026-09-21). 없으면 최근 운영 판정")


def _result(s: Session, replay_day: date | None):
    if replay_day is None:
        return views.find_result(s)
    row = views.find_result(s, replay_day, replay=True)
    if row is None:
        raise HTTPException(404, "그 날짜의 재현 결과가 없음")
    return row


def place_brief(p: Place) -> dict:
    return {"id": p.id, "name": p.name, "district": p.district, "lat": p.lat, "lon": p.lon}


@router.get("/places/search")
def search(q: str = "", lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
           replay_day: date | None = ReplayDay, s: Session = Depends(get_session)):
    """lat·lon(내 위치)을 주면 distance_m을 붙이고 가까운 순, 아니면 가나다순"""
    q = q.strip()
    row = _result(s, replay_day)
    places = {p.id: p for p in s.scalars(select(Place))}
    hits: dict[str, str | None] = {}
    for p in places.values():
        if not q or q in p.name:
            hits[p.id] = None
    if q:
        for a in s.scalars(select(Alias).where(Alias.alias.contains(q))):
            hits.setdefault(a.place_id, a.alias)
    near = lat is not None and lon is not None
    out = []
    for pid, alias in hits.items():
        p = places[pid]
        days = views.crowd_days(row, p)
        dist = distance_m(lat, lon, p.lat, p.lon) if near and p.lat is not None and p.lon is not None else None
        out.append({**place_brief(p), "distance_m": dist, "matched_alias": alias,
                    "tomorrow": days[0] if days else None})
    if near:   # 좌표 없는 장소는 맨 뒤
        return sorted(out, key=lambda x: (x["distance_m"] is None, x["distance_m"] or 0, x["name"]))
    return sorted(out, key=lambda x: x["name"])


def _place_or_404(s: Session, place_id: str) -> Place:
    p = s.get(Place, place_id)
    if not p:
        raise HTTPException(404, "아직 예보가 없는 장소임")
    return p


@router.get("/places/{place_id}/forecast")
def forecast(place_id: str, replay_day: date | None = ReplayDay, s: Session = Depends(get_session)):
    p = _place_or_404(s, place_id)
    row = _result(s, replay_day)
    days = views.crowd_days(row, p)
    return {"meta": views.meta(row) if row else None, "place": place_brief(p),
            "days": days, "least_crowded": views.least_crowded(days),
            # 지금 공지를 과거 날짜에 섞지 않음
            "notices": [] if replay_day else active_notices(s, p.id), "disclaimer": views.DISCLAIMER}


@router.get("/places/{place_id}/forecast/timeslots")
def forecast_timeslots(place_id: str, replay_day: date | None = ReplayDay, s: Session = Depends(get_session)):
    """D+1~3 날짜별 오전·점심·오후·저녁 혼잡. 비율 근거는 method에 담음"""
    p = _place_or_404(s, place_id)
    row = _result(s, replay_day)
    t = time_slots(row, p)
    return {"meta": views.meta(row) if row else None, "place": place_brief(p), **t,
            "disclaimer": views.DISCLAIMER}
