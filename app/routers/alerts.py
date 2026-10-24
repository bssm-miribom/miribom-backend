import json
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import LATEST_KEY, r
from app.config import settings
from app.db import DailyResult, get_session
from app.jobs import run_daily_job

router = APIRouter(tags=["alerts"])


@router.get("/alerts/latest")
def latest(s: Session = Depends(get_session)):
    """가장 최근 판정 결과 (Redis 캐시 → 없으면 DB)"""
    cached = r.get(LATEST_KEY)
    if cached:
        return json.loads(cached)
    row = s.scalars(select(DailyResult).order_by(DailyResult.created_at.desc()).limit(1)).first()
    if not row:
        raise HTTPException(404, "아직 판정 결과가 없음. POST /api/admin/run 으로 한 번 돌려볼 것")
    return row.payload


@router.get("/alerts/{judge_day}")
def by_day(judge_day: date, s: Session = Depends(get_session)):
    row = s.scalars(select(DailyResult).where(DailyResult.judge_day == judge_day)
                    .order_by(DailyResult.created_at.desc()).limit(1)).first()
    if not row:
        raise HTTPException(404, f"{judge_day} 판정 결과 없음")
    return row.payload


@router.post("/admin/run")
async def run_now(judge_day: date | None = None, demo: bool | None = None, x_admin_token: str = Header(default="")):
    """06시를 기다리지 않고 지금 판정 실행. judge_day를 주면 과거 날짜 재현 (A-07)"""
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(401, "관리자 토큰이 틀림")
    try:
        return await run_in_threadpool(run_daily_job, judge_day and str(judge_day), demo)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")
