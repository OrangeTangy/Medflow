import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

class UTCDateTime(TypeDecorator):
    """Keep UTC offsets when using SQLite, which stores timezone-less datetimes."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError('Timestamp must include a timezone offset')
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass
class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
class Tenant(Entity):
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
class Organization(Entity, Base):
    __tablename__='organizations'
    name: Mapped[str] = mapped_column(String(150))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
class Department(Tenant, Base):
    __tablename__='departments'
    name: Mapped[str] = mapped_column(String(100))
    __table_args__=(UniqueConstraint('organization_id','name'),)
class User(Tenant, Base):
    __tablename__='users'
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16), default='doctor')
    department_id: Mapped[str|None] = mapped_column(ForeignKey('departments.id'))
    status: Mapped[str] = mapped_column(String(16), default='active')
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)
    __table_args__=(UniqueConstraint('organization_id','email'),CheckConstraint("role IN ('admin','doctor')"),CheckConstraint("status IN ('active','disabled')"))
class Identity(Entity, Base):
    __tablename__='identity_mappings'
    issuer: Mapped[str] = mapped_column(String(250))
    subject: Mapped[str] = mapped_column(String(250))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    __table_args__=(UniqueConstraint('issuer','subject'),)
class AuthSession(Entity, Base):
    __tablename__='auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
class Location(Tenant, Base):
    __tablename__='locations'
    name: Mapped[str] = mapped_column(String(100))
    building: Mapped[str] = mapped_column(String(150), default='')
    floor: Mapped[str] = mapped_column(String(50), default='')
    timezone: Mapped[str] = mapped_column(String(100), default='UTC')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
class WifiNetwork(Tenant, Base):
    __tablename__='wifi_networks'
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.id'), index=True)
    ssid: Mapped[str] = mapped_column(String(100))
    controller_identifier: Mapped[str] = mapped_column(String(150))
    authentication_configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__=(UniqueConstraint('organization_id','controller_identifier'),)
class Device(Tenant, Base):
    __tablename__='registered_devices'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    device_identifier: Mapped[str] = mapped_column(String(150))
    identity_reference: Mapped[str] = mapped_column(String(250))
    enrollment_status: Mapped[str] = mapped_column(String(16), default='enrolled')
    last_seen: Mapped[datetime|None] = mapped_column(UTCDateTime())
    __table_args__=(UniqueConstraint('organization_id','identity_reference','device_identifier'),)
class NetworkEvent(Tenant, Base):
    __tablename__='network_events'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('registered_devices.id'))
    network_id: Mapped[str] = mapped_column(ForeignKey('wifi_networks.id'))
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.id'))
    event_type: Mapped[str] = mapped_column(String(16))
    source_event_id: Mapped[str] = mapped_column(String(200))
    accounting_session_id: Mapped[str] = mapped_column(String(200))
    event_timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    received_timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    raw_metadata_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(32))
    __table_args__=(UniqueConstraint('organization_id','provider','source_event_id'),CheckConstraint("event_type IN ('start','stop','interim','outage')"),Index('event_replay','organization_id','doctor_id','event_timestamp'))
class AttendanceSession(Tenant, Base):
    __tablename__='attendance_sessions'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.id'))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime|None] = mapped_column(UTCDateTime())
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    confidence_status: Mapped[str] = mapped_column(String(32), default='network_detected')
    session_status: Mapped[str] = mapped_column(String(16), default='open')
    source: Mapped[str] = mapped_column(String(16), default='network')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__=(CheckConstraint('duration_seconds >= 0'),CheckConstraint('ended_at IS NULL OR ended_at >= started_at'),Index('attendance_period','organization_id','doctor_id','started_at'))
class ActivityReport(Tenant, Base):
    __tablename__='activity_reports'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    location_id: Mapped[str|None] = mapped_column(ForeignKey('locations.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)
    original_transcript: Mapped[str] = mapped_column(Text)
    edited_transcript: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(16), default='pending')
class AudioRecording(Tenant, Base):
    __tablename__='audio_recordings'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    report_id: Mapped[str|None] = mapped_column(ForeignKey('activity_reports.id'))
    storage_reference: Mapped[str] = mapped_column(String(500))
    recording_duration: Mapped[int] = mapped_column(Integer, default=0)
    retention_expiration: Mapped[datetime] = mapped_column(UTCDateTime())
class Correction(Tenant, Base):
    __tablename__='attendance_corrections'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    session_id: Mapped[str|None] = mapped_column(ForeignKey('attendance_sessions.id', ondelete='SET NULL'))
    requested_changes: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(16), default='pending')
    reviewed_by: Mapped[str|None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime|None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
class AuditLog(Tenant, Base):
    __tablename__='audit_logs'
    actor_id: Mapped[str|None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str|None] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    outcome: Mapped[str] = mapped_column(String(20), default='success')
    details: Mapped[dict] = mapped_column('metadata', JSON, default=dict)
class ProcessingJob(Tenant, Base):
    __tablename__='processing_jobs'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default='queued')
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str|None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)
