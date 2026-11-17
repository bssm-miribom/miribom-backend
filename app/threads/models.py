"""Threads 콜백 테이블"""
from datetime import datetime

from sqlalchemy import (DateTime, Integer, String, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DeletionRequest(Base):
    """Threads 데이터 삭제 요청 기록 (확인 코드로 상태 조회)"""
    __tablename__ = "deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # deauthorize | delete
    status: Mapped[str] = mapped_column(String(16), default="done")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

