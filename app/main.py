import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.ai.router import router as ai
from app.auth.router import router as auth
from app.citizen.router import router as citizen
from app.core.config import settings
from app.core.db import init_db
from app.core.seed import seed
from app.dashboard.router import router as dashboard
from app.health.router import router as health
from app.judge import runtime
from app.judge.jobs import start_scheduler, stop_scheduler
from app.judge.router import router as judge
from app.notices.router import router as notices
from app.places.router import router as places
from app.response.router import router as response
from app.scenario.router import router as scenario
from app.threads.demo import router as threads_demo
from app.threads.router import router as threads

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.prepare()
    init_db()
    seed()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="미리봄 API", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (health, auth, dashboard, places, judge, scenario, response, notices, citizen, ai, threads):
    app.include_router(r, prefix="/api")

# Threads 로그인·검색 화면 (Meta 심사 녹화용). 콜백 주소가 /threads/callback이라 /api를 붙이지 않음
app.include_router(threads_demo)

STATIC = Path(__file__).parent / "static"


@app.get("/privacy", include_in_schema=False)
def privacy():
    return FileResponse(STATIC / "privacy.html")
