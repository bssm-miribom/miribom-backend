import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import runtime
from app.config import settings
from app.db import init_db
from app.jobs import start_scheduler, stop_scheduler
from app.routers import admin, auth, health, public, threads, threads_demo
from app.seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.prepare()
    init_db()
    seed()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="미리봄 API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (health, auth, admin, public, threads):
    app.include_router(r.router, prefix="/api")

# Threads 로그인·검색 화면 (Meta 심사 녹화용). 콜백 주소가 /threads/callback이라 /api를 붙이지 않음
app.include_router(threads_demo.router)

STATIC = Path(__file__).parent / "static"


@app.get("/privacy", include_in_schema=False)
def privacy():
    return FileResponse(STATIC / "privacy.html")
