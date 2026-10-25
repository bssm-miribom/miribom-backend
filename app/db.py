from datetime import datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine,
                        func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
JSONType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class Place(Base):
    """추적 장소. 처음 실행 때 miribom-ai/places.csv로 채움"""
    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    district: Mapped[str | None] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    keywords: Mapped[str] = mapped_column(Text)          # 기본 검색어, | 로 구분 (별칭은 aliases 표)
    base_rest: Mapped[float | None] = mapped_column(Float)
    base_work: Mapped[float | None] = mapped_column(Float)
    bottleneck_name: Mapped[str | None] = mapped_column(String(60))
    bottleneck_m2: Mapped[float | None] = mapped_column(Float)
    peak_share: Mapped[float | None] = mapped_column(Float)
    bottleneck_share: Mapped[float | None] = mapped_column(Float)
    force_watch: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)


class Alias(Base):
    """'부캉이' 같은 새 별칭 (A-06)"""
    __tablename__ = "aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(String(60), unique=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    """기관 계정 (A-15). org_type: city | district | facility"""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    org_name: Mapped[str] = mapped_column(String(60))
    org_type: Mapped[str] = mapped_column(String(16))
    district: Mapped[str | None] = mapped_column(String(20))
    place_ids: Mapped[list | None] = mapped_column(JSONType)   # facility 계정의 관리 시설


class DailyResult(Base):
    """하루 판정 결과 (miribom_ai.run_daily()가 돌려준 dict 통째로). replay=True는 과거 사례 재현"""
    __tablename__ = "daily_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    judge_day: Mapped[datetime] = mapped_column(Date, index=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    replay: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    payload: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notice(Base):
    """시민 화면 공지 (A-13)"""
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    place_id: Mapped[str | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    with engine.begin() as c:   # v0.1 DB에 없던 칸
        c.execute(text("ALTER TABLE daily_results ADD COLUMN IF NOT EXISTS replay boolean NOT NULL DEFAULT false"))


def get_session():
    with SessionLocal() as s:
        yield s
