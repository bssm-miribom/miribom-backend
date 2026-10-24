from fastapi import APIRouter
from sqlalchemy import text

from app.cache import r
from app.db import engine
from app.jobs import scheduler

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    out = {"status": "ok"}
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        out["db"] = "ok"
    except Exception as e:
        out["db"], out["status"] = f"error: {type(e).__name__}", "degraded"
    try:
        r.ping()
        out["redis"] = "ok"
    except Exception as e:
        out["redis"], out["status"] = f"error: {type(e).__name__}", "degraded"
    job = scheduler.get_job("daily") if scheduler.running else None
    out["next_daily_run"] = job.next_run_time.isoformat() if job else None
    return out
