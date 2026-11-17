"""판정 결과·실행 기록 테이블"""
from datetime import datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType


class DailyResult(Base):
    """하루 판정 결과 (miribom_ai.run_daily()가 돌려준 dict 통째로). replay=True는 과거 사례 재현"""
    __tablename__ = "daily_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    judge_day: Mapped[datetime] = mapped_column(Date, index=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    replay: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    payload: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class DailyRun(Base):
    """판정 실행 기록 (06시·수동·재현). 실패도 남김"""
    __tablename__ = "daily_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(16))           # schedule | manual | replay
    judge_day: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="running")   # running | ok | failed
    result_id: Mapped[int | None] = mapped_column(ForeignKey("daily_results.id", ondelete="SET NULL"))
    places: Mapped[int | None] = mapped_column(Integer)
    failed: Mapped[int | None] = mapped_column(Integer)
    intent: Mapped[str | None] = mapped_column(Text)            # 의도 수집 결과 문장 (건너뜀·실패 이유)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

