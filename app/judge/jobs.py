"""매일 06시 판정 작업
순서: (선택) 어제 Threads 글 → 가볼래 글 수 → miribom_ai.run_daily (급증 탐지 → 규모 예측 → 경보) → 저장·캐시 → 2단계 이상 알림
서버는 저장·캐시·알림만 하고 계산은 miribom_ai가 함"""
import json
import logging
import os
from datetime import date, datetime, time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.cache import LATEST_KEY, LOCK_KEY, r
from app.core.config import KST, settings
from app.core.db import SessionLocal
from app.judge import runtime
from app.judge.models import DailyResult, DailyRun

log = logging.getLogger("miribom.jobs")
scheduler = BackgroundScheduler(timezone=KST)


class JobBusy(RuntimeError):
    """06시 작업이나 다른 수동 실행이 이미 돌고 있음"""


def collect_intent() -> str:
    """어제 글을 모아 장소별 가볼래 글 수를 저장. 실패해도 판정은 계속함 (의도 글 수만 빠짐)"""
    if not settings.intent_collect:
        return "건너뜀: INTENT_COLLECT=false"
    token = settings.threads_access_token or os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        return "건너뜀: THREADS_ACCESS_TOKEN 없음"
    try:
        from miribom_ai.intent.daily import run
        return f"저장 {run(token=token)}줄"
    except Exception as e:   # torch 미설치, 모델 없음, Threads 오류 등
        log.exception("의도 수집 실패")
        return f"실패: {type(e).__name__}: {str(e)[:150]}"


def run_daily_job(judge_day: date | None = None, demo: bool | None = None, replay: bool = False,
                  trigger: str = "manual") -> DailyResult:
    import miribom_ai  # pandas·lightgbm이 무거워서 쓸 때 불러옴

    demo = settings.miribom_demo if demo is None else demo
    # 같은 작업이 겹쳐 돌지 않게 Redis 잠금 (최대 30분)
    if not r.set(LOCK_KEY, "1", nx=True, ex=1800):
        raise JobBusy("판정 작업이 이미 실행 중임. 잠시 뒤 다시 시도할 것")
    try:
        with SessionLocal() as s:
            run = DailyRun(trigger="replay" if replay else trigger, judge_day=judge_day, status="running")
            s.add(run)
            s.commit()
            try:
                # 재현은 판정일 07시 전에 등록된 별칭만 씀
                cutoff = datetime.combine(judge_day, time(7), KST) if replay and judge_day else None
                runtime.write_places(s, alias_before=cutoff)
                if not replay and not demo and judge_day is None:   # 오늘 운영 판정일 때만 새 글을 모음
                    run.intent = collect_intent()
                payload = miribom_ai.run_daily(judge_day and str(judge_day), demo=demo, save=False)
                row = DailyResult(judge_day=date.fromisoformat(payload["판정일"]), demo=demo, replay=replay,
                                  payload=payload)
                s.add(row)
                s.flush()
                run.result_id, run.judge_day, run.status = row.id, row.judge_day, "ok"
                run.places = len(payload["장소"])
                run.failed = sum(p.get("단계") == "수집 실패" for p in payload["장소"])
            except Exception as e:
                run.status, run.error = "failed", f"{type(e).__name__}: {str(e)[:500]}"
                raise
            finally:
                run.finished_at = datetime.now(KST)
                s.commit()
        if not replay:
            r.set(LATEST_KEY, json.dumps({"id": row.id}))
            _notify(row.id)
        log.info("판정 완료 %s (장소 %d곳, demo=%s, replay=%s)", payload["판정일"], len(payload["장소"]), demo, replay)
        return row
    finally:
        r.delete(LOCK_KEY)


def _notify(result_id: int):
    """2단계 이상 장소를 관할 기관에 알림 (A-12). 실패해도 판정 결과는 그대로 둠"""
    from app.response.notify import auto_notify
    try:
        with SessionLocal() as s:
            n = auto_notify(s, s.get(DailyResult, result_id))
            if n:
                log.info("경보 알림 %d건 (%s)", n, settings.notify_mode)
    except Exception:
        log.exception("경보 알림 실패")


def _scheduled():
    try:
        run_daily_job(trigger="schedule")
    except Exception:
        log.exception("06시 판정 실패")


def start_scheduler():
    if not settings.scheduler_enabled:
        return
    # CronTrigger는 스케줄러 시간대를 안 따라가서 직접 넣어야 함
    scheduler.add_job(_scheduled, CronTrigger(hour=settings.daily_hour, minute=settings.daily_minute, timezone=KST),
                      id="daily", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    log.info("예약 등록: 매일 %02d:%02d (Asia/Seoul)", settings.daily_hour, settings.daily_minute)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
