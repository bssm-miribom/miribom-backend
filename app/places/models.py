"""장소·별칭 테이블"""
from datetime import datetime

from sqlalchemy import (DateTime, Float, ForeignKey, Integer, String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType


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
    bottleneck_polygon: Mapped[list | None] = mapped_column(JSONType)   # [[경도, 위도], ...] (A-08)



class Alias(Base):
    """'부캉이' 같은 새 별칭 (A-06)"""
    __tablename__ = "aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(String(60), unique=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

