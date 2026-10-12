from datetime import datetime
from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_node_received", "node_id", "received_at"),
        Index("ix_readings_received_at", "received_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    node_id: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    value_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status_code: Mapped[str] = mapped_column(String(128), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
