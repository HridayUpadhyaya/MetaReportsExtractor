from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), default="sync")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(80), default="India")
    pdf_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    period_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    report_published: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(30), default="new")
    validation_status: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    rows: Mapped[list["NormalizedRow"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class NormalizedRow(Base):
    __tablename__ = "normalized_rows"
    __table_args__ = (
        UniqueConstraint("report_id", "platform", "policy_category", name="uq_report_platform_category"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    report_published: Mapped[str | None] = mapped_column(String(80), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    raw_policy_category: Mapped[str] = mapped_column(Text)
    policy_category: Mapped[str] = mapped_column(Text, index=True)
    content_actioned_raw: Mapped[str] = mapped_column(String(80))
    content_actioned_numeric: Mapped[float] = mapped_column(Float)
    proactive_rate: Mapped[float] = mapped_column(Float)
    total_user_grievances: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(40), default="deterministic")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    validation_status: Mapped[str] = mapped_column(String(30), default="ok")
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[Report] = relationship(back_populates="rows")


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_key: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
