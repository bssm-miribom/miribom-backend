from datetime import datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, String, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class DailyResult(Base):
    """하루 판정 결과 (miribom_ai.run_daily()가 돌려준 dict 통째로)"""
    __tablename__ = "daily_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    judge_day: Mapped[datetime] = mapped_column(Date, index=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeletionRequest(Base):
    """Threads 데이터 삭제 요청 기록 (확인 코드로 상태 조회)"""
    __tablename__ = "deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # deauthorize | delete
    status: Mapped[str] = mapped_column(String(16), default="done")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def init_db():
    # 지금은 시작할 때 테이블만 만듦. 스키마가 자주 바뀌면 Alembic으로 옮김
    Base.metadata.create_all(engine)


def get_session():
    with SessionLocal() as s:
        yield s
