"""관리자 대시보드 (A-01~A-05, A-09): 지도·요약, 급상승 목록, 장소 상세"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.models import Account
from app.auth.service import can_see, current_account
from app.core.db import get_session
from app.dashboard import views
from app.places.models import Place

router = APIRouter(prefix="/admin", tags=["대시보드"])


SCENARIO = Query(None, description="가상 시나리오 키 (POST /admin/scenario 응답의 meta.scenario.key)")


def _check_replay(replay: bool, acc: Account, scenario: str | None = None):
    if (replay or scenario) and acc.org_type != "city":
        raise HTTPException(403, "과거 사례 재현·가상 시나리오는 부산시 계정만 볼 수 있음")


@router.get("/dashboard")
def dashboard(judge_day: date | None = None, replay: bool = False, scenario: str | None = SCENARIO,
              acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    _check_replay(replay, acc, scenario)
    return views.dashboard(s, views.result_or_404(s, judge_day, replay, scenario), acc)


@router.get("/dashboard/rising")
def dashboard_rising(judge_day: date | None = None, replay: bool = False, scenario: str | None = SCENARIO,
                     stage: Literal["stage3", "stage2"] | None = None,
                     acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    """A-03 급상승 장소 목록. 3단계·2단계만 (1단계·판정 보류·수집 실패는 빠짐)"""
    _check_replay(replay, acc, scenario)
    return views.rising(s, views.result_or_404(s, judge_day, replay, scenario), acc, stage)


@router.get("/places/{place_id}")
def place_detail(place_id: str, judge_day: date | None = None, replay: bool = False, scenario: str | None = SCENARIO,
                 acc: Account = Depends(current_account), s: Session = Depends(get_session)):
    place = s.get(Place, place_id)
    if not place or not can_see(acc, place):
        raise HTTPException(404, "없는 장소")
    _check_replay(replay, acc, scenario)
    return views.place_detail(s, views.result_or_404(s, judge_day, replay, scenario), place)
