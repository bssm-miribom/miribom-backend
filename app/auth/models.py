"""기관 계정 테이블"""

from sqlalchemy import (Integer, String)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType


class Account(Base):
    """기관 계정 (A-15). org_type: city | district | facility | police"""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    org_name: Mapped[str] = mapped_column(String(60))
    org_type: Mapped[str] = mapped_column(String(16))
    district: Mapped[str | None] = mapped_column(String(20))
    place_ids: Mapped[list | None] = mapped_column(JSONType)   # facility: 관리 시설, police: 조치 요청 받은 장소

