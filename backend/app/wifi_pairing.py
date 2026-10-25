"""Opt-in device pairing and durable notifications for the local test runtime.

These device reports never enter trusted RADIUS reconciliation or attendance.
The receiver exposes only a scoped write capability, not local account APIs.
"""
from datetime import datetime, timedelta, timezone
import ipaddress
import secrets
from urllib.parse import urlsplit
from uuid import UUID
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from .local_models import LocalPairedDevice, LocalNotification
from .models import User, now
from .security import token_hash
from .services import scope, audit, get_record


def validate_receiver_url(value):
    value = value.rstrip('/')
    url = urlsplit(value)
    if not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError('Use a receiver base URL without credentials or paths')
    try:
        url.port
    except ValueError:
        raise ValueError('Invalid receiver port')
    if url.scheme == 'https':
        return value
    if url.scheme == 'http':
        try:
            address = ipaddress.ip_address(url.hostname)
            private = address.version == 4 and (address in ipaddress.ip_network('10.0.0.0/8') or address in ipaddress.ip_network('172.16.0.0/12') or address in ipaddress.ip_network('192.168.0.0/16') or address.is_loopback)
        except ValueError:
            private = url.hostname == 'localhost'
        if private:
            return value
    raise ValueError('Use HTTPS, or an explicit private IPv4 address for a LAN-only HTTP test')


class PairDevice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=128)
    target_ssid: str = Field(min_length=1, max_length=128)
    receiver_url: str = Field(max_length=2048)
    doctor_id: str | None = None

    @field_validator('target_ssid')
    @classmethod
    def ssid_length(cls, value):
        if len(value.encode('utf-8')) > 32:
            raise ValueError('A WiFi SSID is at most 32 UTF-8 bytes')
        return value

    @field_validator('receiver_url')
    @classmethod
    def receiver(cls, value):
        return validate_receiver_url(value)


class DeviceEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    event_type: Literal['connected', 'disconnected', 'unknown', 'monitor_started', 'monitor_stopped']
    observed_at: datetime
    ssid: str | None = Field(default=None, max_length=128)
    initial_observation: bool = False
    note: str | None = Field(default=None, max_length=500)

    @field_validator('observed_at')
    @classmethod
    def observed_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Include a timezone in the observation timestamp')
        value = value.astimezone(timezone.utc)
        if value > now()+timedelta(seconds=60) or value < now()-timedelta(days=30):
            raise ValueError('Observation must be within the last 30 days and not in the future')
        return value


def register_pairing_routes(app, local_principal, local_database):
    @app.post('/api/local/devices', status_code=201)
    def pair(body: PairDevice, p=Depends(local_principal), db=Depends(local_database)):
        doctor_id = body.doctor_id or p.id
        if p.role != 'admin' and doctor_id != p.id:
            raise HTTPException(403, 'You can pair only your own device')
        doctor = get_record(db, User, doctor_id, p)
        if doctor.role != 'doctor' or doctor.status != 'active':
            raise HTTPException(422, 'Select an active doctor account')
        token = secrets.token_urlsafe(32)
        row = LocalPairedDevice(organization_id=p.organization_id, doctor_id=doctor.id, name=body.name, target_ssid=body.target_ssid, token_hash=token_hash(token))
        db.add(row); db.flush()
        audit(db, p, 'pair', 'wifi_device', row.id)
        db.commit()
        return {'id': row.id, 'pairing': {'version': 1, 'receiver_url': body.receiver_url, 'token': token, 'device_id': row.id, 'ssid': row.target_ssid}, 'warning': 'Keep this one-time pairing token private. Device reports are unverified.'}

    @app.get('/api/local/devices')
    def devices(p=Depends(local_principal), db=Depends(local_database)):
        return [{'id': d.id, 'doctor_id': d.doctor_id, 'name': d.name, 'target_ssid': d.target_ssid, 'last_state': d.last_state, 'last_observed_at': d.last_observed_at, 'last_received_at': d.last_received_at, 'revoked_at': d.revoked_at} for d in db.scalars(scope(LocalPairedDevice, p).order_by(LocalPairedDevice.created_at.desc()))]

    @app.post('/api/local/devices/{device_id}/revoke')
    def revoke(device_id: str, p=Depends(local_principal), db=Depends(local_database)):
        row = get_record(db, LocalPairedDevice, device_id, p)
        row.revoked_at = row.revoked_at or now()
        audit(db, p, 'revoke', 'wifi_device', row.id)
        db.commit()
        return {'revoked': True}

    @app.get('/api/local/notifications')
    def notifications(after: int | None = Query(default=None, ge=0), p=Depends(local_principal), db=Depends(local_database)):
        q = scope(LocalNotification, p)
        if after is not None:
            rows = db.scalars(q.where(LocalNotification.id > after).order_by(LocalNotification.id).limit(100)).all()
        else:
            rows = list(reversed(db.scalars(q.order_by(LocalNotification.id.desc()).limit(50)).all()))
        return [{'id': row.id, 'device_id': row.device_id, 'title': row.title, 'message': row.message, 'observed_at': row.observed_at, 'received_at': row.created_at, 'evidence': 'device_reported_test'} for row in rows]
