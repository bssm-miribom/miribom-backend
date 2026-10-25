"""매일 06시 판정 작업. miribom_ai가 수집 → 급증 탐지 → 규모 예측 → 경보까지 하고, 서버는 저장·캐시만 함"""
import json
import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import runtime
from app.cache import LATEST_KEY, LOCK_KEY, r
from app.config import settings
from app.db import DailyResult, SessionLocal

log = logging.getLogger("miribom.jobs")
KST = ZoneInfo("Asia/Seoul")
scheduler = BackgroundScheduler(timezone=KST)


def run_daily_job(judge_day: date | None = None, demo: bool | None = None, replay: bool = False) -> DailyResult:
    import miribom_ai  # pandas·lightgbm이 무거워서 쓸 때 불러옴

    demo = settings.miribom_demo if demo is None else demo
    # 같은 작업이 겹쳐 돌지 않게 Redis 잠금 (최대 30분)
    if not r.set(LOCK_KEY, "1", nx=True, ex=1800):
        raise RuntimeError("판정 작업이 이미 실행 중임")
    try:
        with SessionLocal() as s:
            # 재현은 판정일 07시 전에 등록된 별칭만 씀
            cutoff = datetime.combine(judge_day, time(7), KST) if replay and judge_day else None
            runtime.write_places(s, alias_before=cutoff)
            payload = miribom_ai.run_daily(judge_day and str(judge_day), demo=demo, save=False)
            row = DailyResult(judge_day=date.fromisoformat(payload["판정일"]), demo=demo, replay=replay, payload=payload)
            s.add(row)
            s.commit()
        if not replay:
            r.set(LATEST_KEY, json.dumps({"id": row.id}))
        log.info("판정 완료 %s (장소 %d곳, demo=%s, replay=%s)", payload["판정일"], len(payload["장소"]), demo, replay)
        return row
    finally:
        r.delete(LOCK_KEY)


def _scheduled():
    try:
        run_daily_job()
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
