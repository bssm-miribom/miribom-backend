"""대응·점검표·알림·실측 회신 테이블"""
from datetime import datetime

from sqlalchemy import (Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType


class Response(Base):
    """부산시가 정한 대응 수준과 조치 요청 (A-11). 장소·판정일마다 마지막 것이 유효"""
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    judge_day: Mapped[datetime] = mapped_column(Date, index=True)
    level: Mapped[str] = mapped_column(String(16))              # none | stage1 | stage2 | stage3
    note: Mapped[str | None] = mapped_column(Text)
    request_to: Mapped[list | None] = mapped_column(JSONType)  # 조치 요청한 계정 username
    decided_by: Mapped[str] = mapped_column(String(40))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class Checklist(Base):
    """대응 점검표 (A-10, B-03). items = [{id, label, done, by, at}]"""
    __tablename__ = "checklists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    judge_day: Mapped[datetime] = mapped_column(Date, index=True)
    level: Mapped[str] = mapped_column(String(16))
    items: Mapped[list] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class Contact(Base):
    """기관별 알림 받는 곳 (A-12)"""
    __tablename__ = "contacts"

    org: Mapped[str] = mapped_column(String(40), primary_key=True)   # 계정 username
    channel: Mapped[str] = mapped_column(String(16))                 # sms | kakao | email
    to: Mapped[str] = mapped_column(String(200))



class Notification(Base):
    """보낸 경보 알림 기록 (A-12, B-01). 시연은 실제 발송 없이 dry_run"""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    judge_day: Mapped[datetime] = mapped_column(Date, index=True)
    org: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str | None] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))   # dry_run | sent | failed | no_contact
    reason: Mapped[str] = mapped_column(String(16), default="auto")   # auto | request
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class VisitorReport(Base):
    """협력 기관이 회신한 장소별 실측 방문객 (A-14, B-04)"""
    __tablename__ = "visitor_reports"
    __table_args__ = (UniqueConstraint("place_id", "date", "org"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(Date)
    visitors: Mapped[int] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    org: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

