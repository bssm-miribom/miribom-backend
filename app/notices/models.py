"""시민 공지 테이블"""
from datetime import datetime

from sqlalchemy import (DateTime, ForeignKey, Integer, String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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

