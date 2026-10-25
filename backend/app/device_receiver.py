"""Narrow, bearer-authenticated WiFi receiver; no login or dashboard routes."""
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .local_models import LocalPairedDevice, LocalWifiEvent, LocalNotification
from .models import User, AuditLog, now
from .security import token_hash
from .wifi_pairing import DeviceEvent


def create_receiver(engine):
    app = FastAPI(title='Medflow Device Receiver', docs_url=None, redoc_url=None, openapi_url=None)
    buckets = defaultdict(deque)

    @app.middleware('http')
    async def boundary(request, call_next):
        if request.headers.get('origin'):
            return JSONResponse({'detail': 'Use a paired native client'}, 403)
        if request.method == 'POST':
            # Read with a strict bound, including chunked bodies with no length.
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 8192:
                    return JSONResponse({'detail': 'Event too large'}, 413)
            request._body = bytes(data)
            key = (request.client.host if request.client else 'unknown')
            if key not in buckets and len(buckets) >= 2048:
                buckets.clear()
            bucket, stamp = buckets[key], time.monotonic()
            while bucket and bucket[0] < stamp-60:
                bucket.popleft()
            if len(bucket) >= 240:
                return JSONResponse({'detail': 'Rate limit reached'}, 429)
            bucket.append(stamp)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse({'detail': 'Conflicting event ID; retry with the original payload'}, 409)

    @app.exception_handler(OperationalError)
    async def busy(request, exc):
        return JSONResponse({'detail': 'Database busy; retry later'}, 503)

    @app.get('/health')
    def health():
        return {'status': 'ready', 'service': 'wifi-device-receiver'}

    @app.post('/api/events')
    def ingest(body: DeviceEvent, request: Request):
        auth = request.headers.get('authorization', '')
        if not auth.startswith('Bearer ') or len(auth) > 200:
            raise HTTPException(401, 'A paired device token is required')
        with Session(engine, expire_on_commit=False) as db:
            db.execute(text('BEGIN IMMEDIATE'))
            device = db.scalar(select(LocalPairedDevice).where(LocalPairedDevice.token_hash == token_hash(auth[7:])))
            if not device or device.revoked_at:
                raise HTTPException(401, 'Invalid or revoked pairing')
            doctor = db.get(User, device.doctor_id)
            if not doctor or doctor.status != 'active' or doctor.role != 'doctor' or doctor.organization_id != device.organization_id:
                raise HTTPException(401, 'The paired account is disabled')
            if body.event_type in ('connected', 'disconnected') and body.ssid != device.target_ssid:
                raise HTTPException(422, 'Observation does not match the paired WiFi network')
            payload = {**body.model_dump(mode='json', exclude_none=True), 'device_id': device.id, 'source': 'paired_device_test'}
            existing = db.get(LocalWifiEvent, str(body.id))
            if existing:
                if existing.device_id != device.id or existing.payload != payload:
                    raise HTTPException(409, 'Event ID already belongs to a different observation')
                return {'id': existing.id, 'duplicate': True}
            received = now()
            event = LocalWifiEvent(id=str(body.id), organization_id=device.organization_id, doctor_id=device.doctor_id, device_id=device.id, run_id=device.id, event_type=body.event_type, observed_at=body.observed_at, received_at=received, payload=payload)
            db.add(event); db.flush()
            device.last_received_at = received
            if device.last_observed_at is None or body.observed_at >= device.last_observed_at:
                device.last_observed_at = body.observed_at
                device.last_state = body.event_type if body.event_type in ('connected', 'disconnected') else 'unknown'
            if body.event_type in ('connected', 'disconnected'):
                label = 'WiFi baseline' if body.initial_observation else 'WiFi '+body.event_type
                title = f'{doctor.full_name[:100]} · {label}'
                direction = 'to' if body.event_type == 'connected' else 'from'
                message = f'{device.name}: {body.event_type} {direction} {device.target_ssid}. Phone/computer time: {body.observed_at.isoformat()}. Device-reported; not physically verified.'
                db.add(LocalNotification(organization_id=device.organization_id, doctor_id=device.doctor_id, device_id=device.id, event_id=event.id, title=title, message=message, observed_at=body.observed_at, created_at=received))
            db.add(AuditLog(organization_id=device.organization_id, actor_id=device.doctor_id, action='device:ingest', resource_type='wifi_test_event', resource_id=event.id, details={'device_id': device.id}))
            db.commit()  # Acknowledge only once event + notification are durable.
            return {'id': event.id, 'duplicate': False, 'received_at': received, 'attendance_modified': False}

    return app


def create_app():
    # Share only SQLite storage with the loopback application, not its routes.
    from .local import create_local_app
    local = create_local_app(os.environ.get('MEDFLOW_LOCAL_DB'))
    return create_receiver(local.state.engine)
