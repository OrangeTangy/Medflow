"""Tables used only by the explicit localhost runtime, never hospital OIDC auth."""
from datetime import datetime
from sqlalchemy import String, Integer, JSON, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .models import User, Organization, Location, AttendanceSession, UTCDateTime, now, uid


class LocalBase(DeclarativeBase):
    pass


class LocalCredential(LocalBase):
    __tablename__ = 'local_credentials'
    user_id: Mapped[str] = mapped_column(ForeignKey(User.__table__.c.id), primary_key=True)
    salt: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(128))


class LocalTimestamp(LocalBase):
    __tablename__ = 'local_timestamps'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey(Organization.__table__.c.id), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey(User.__table__.c.id), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey(Location.__table__.c.id))
    session_id: Mapped[str | None] = mapped_column(ForeignKey(AttendanceSession.__table__.c.id, ondelete='SET NULL'))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    event_type: Mapped[str] = mapped_column(String(16))
    source_event_id: Mapped[str] = mapped_column(String(128))
    event_timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    received_timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    recorded_by: Mapped[str] = mapped_column(ForeignKey(User.__table__.c.id))
    __table_args__ = (
        UniqueConstraint('organization_id', 'source_event_id'),
        CheckConstraint("event_type IN ('arrival','departure')"),
    )


class LocalWifiEvent(LocalBase):
    __tablename__ = 'local_wifi_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey(Organization.__table__.c.id), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey(User.__table__.c.id), index=True)
    device_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    payload: Mapped[dict] = mapped_column(JSON)
