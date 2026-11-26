"""가상 시나리오 API (부산시만 실행). 조회는 다른 API에 ?scenario=<key>를 붙여서 함"""
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import Account
from app.auth.service import city_account
from app.core.cache import r
from app.core.db import get_session
from app.dashboard import views
from app.scenario import service

router = APIRouter(prefix="/admin", tags=["가상 시나리오"])


class ScenarioIn(BaseModel):
    judge_day: date = date(2026, 9, 21)
    place_id: str = "bukhang"
    multiplier: float = Field(1.0, ge=1, le=10, description="그 장소 검색 지수를 몇 배로 키울지")
    start: date | None = Field(None, description="이 날부터 키움. 없으면 판정일 3일 전")
    force: bool = False


@router.post("/scenario")
async def run_scenario(body: ScenarioIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    """가상 시나리오 실행 → 대시보드 모양 + meta.scenario. 같은 조건은 저장된 결과 (force면 다시).
    meta.scenario.key를 /admin/dashboard, /admin/places/{id}, 시민 API에 ?scenario=로 넘기면 같은 결과를 봄"""
    key = service.key_of(body.judge_day, body.place_id, body.multiplier)
    if body.force or not r.exists(service.KEY.format(key)):
        key = await run_in_threadpool(service.run, body.judge_day, body.place_id, body.multiplier, body.start)
    return views.dashboard(s, service.load(key), acc)
