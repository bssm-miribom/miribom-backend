"""판정 실행·재현 (S-01~S-05, A-07)과 실행 기록"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Account
from app.auth.service import city_account, city_or_token
from app.core.config import KST
from app.core.db import get_session
from app.dashboard import views
from app.judge.jobs import JobBusy, run_daily_job
from app.judge.models import DailyResult, DailyRun

router = APIRouter(prefix="/admin", tags=["판정·재현"])


class ReplayIn(BaseModel):
    judge_day: date
    force: bool = False


async def _run(**kw):
    try:
        return await run_in_threadpool(run_daily_job, **kw)
    except JobBusy as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@router.post("/replay")
async def replay(body: ReplayIn, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    """그날 07시까지 받을 수 있던 자료만으로 판정을 다시 돌림. 이미 돌린 날짜는 저장된 결과 (force면 다시)"""
    if body.judge_day > datetime.now(KST).date():
        raise HTTPException(400, "미래 날짜는 재현할 수 없음")
    row = None if body.force else views.find_result(s, body.judge_day, replay=True)
    if row is None:
        row = await _run(judge_day=body.judge_day, replay=True)
    return views.dashboard(s, s.get(DailyResult, row.id), acc)


@router.post("/run")
async def run_now(who: str = Depends(city_or_token), s: Session = Depends(get_session)):
    """06시를 기다리지 않고 오늘 판정을 지금 실행"""
    row = await _run(trigger="manual")
    city = s.scalars(select(Account).where(Account.org_type == "city")).first()
    return views.dashboard(s, s.get(DailyResult, row.id), city)


@router.get("/runs")
def runs(limit: int = 20, acc: Account = Depends(city_account), s: Session = Depends(get_session)):
    """판정 실행 기록 (06시·수동·재현, 실패 포함). 최근 순"""
    q = select(DailyRun).order_by(DailyRun.started_at.desc(), DailyRun.id.desc()).limit(min(max(limit, 1), 200))
    return [{"id": x.id, "trigger": x.trigger, "judge_day": str(x.judge_day) if x.judge_day else None,
             "status": x.status, "result_id": x.result_id, "places": x.places, "failed": x.failed,
             "intent": x.intent, "error": x.error, "started_at": x.started_at.isoformat() if x.started_at else None,
             "finished_at": x.finished_at.isoformat() if x.finished_at else None}
            for x in s.scalars(q)]
