"""매일 06시 판정 작업. miribom_ai가 수집 → 급증 탐지 → 규모 예측 → 경보까지 하고, 서버는 저장·캐시만 함"""
import json
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.cache import LATEST_KEY, LOCK_KEY, r
from app.config import settings
from app.db import DailyResult, SessionLocal

log = logging.getLogger("miribom.jobs")
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def run_daily_job(judge_day: str | None = None, demo: bool | None = None) -> dict:
    import miribom_ai  # pandas·lightgbm이 무거워서 쓸 때 불러옴

    demo = settings.miribom_demo if demo is None else demo
    # 같은 작업이 겹쳐 돌지 않게 Redis 잠금 (최대 30분)
    if not r.set(LOCK_KEY, "1", nx=True, ex=1800):
        raise RuntimeError("판정 작업이 이미 실행 중임")
    try:
        payload = miribom_ai.run_daily(judge_day, demo=demo, save=False)
        with SessionLocal() as s:
            s.add(DailyResult(judge_day=payload["판정일"], demo=demo, payload=payload))
            s.commit()
        if judge_day is None:  # 과거 재현은 최신값을 덮지 않음
            r.set(LATEST_KEY, json.dumps(payload, ensure_ascii=False))
        log.info("판정 완료 %s (장소 %d곳, demo=%s)", payload["판정일"], len(payload["장소"]), demo)
        return payload
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
    scheduler.add_job(_scheduled, CronTrigger(hour=settings.daily_hour, minute=settings.daily_minute, timezone="Asia/Seoul"),
                      id="daily", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    log.info("예약 등록: 매일 %02d:%02d (Asia/Seoul)", settings.daily_hour, settings.daily_minute)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
