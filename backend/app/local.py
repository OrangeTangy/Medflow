"""Single-computer runtime. Start with scripts/run_local.py; binds loopback only.

It reuses the real API/business models, adds explicit local password accounts,
and stores manual timestamps in SQLite. No fake attendance or WiFi events.
"""
import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Depends, HTTPException, Request, APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from .models import Base, Organization, Department, User, Location, WifiNetwork, AuthSession, AttendanceSession, AuditLog, now, uid
from .local_models import LocalBase, LocalCredential, LocalTimestamp
from .security import Principal, principal, database, guard_mutation, token_hash
from .services import audit, dashboard, get_record, json_row, scope


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Setup(Strict):
    organization: str = Field(default='My Hospital', min_length=2, max_length=100)
    admin_name: str = Field(min_length=2, max_length=100)
    admin_email: str = Field(default='admin@local.test', pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    admin_password: str = Field(min_length=10, max_length=200)
    doctor_name: str = Field(min_length=2, max_length=100)
    doctor_email: str = Field(default='doctor@local.test', pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    doctor_password: str = Field(min_length=10, max_length=200)
    location: str = Field(default='Main Hospital', min_length=2, max_length=100)
    timezone: str = 'UTC'

    @field_validator('timezone')
    @classmethod
    def timezone_valid(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError('Use a valid IANA timezone, such as America/New_York')
        return value


class Login(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class LocalAccount(Strict):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    department: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=200)


class TimestampInput(Strict):
    event_type: str
    location_id: str
    doctor_id: str | None = None
    event_timestamp: datetime | None = None
    source_event_id: str = Field(default_factory=uid, min_length=1, max_length=128)

    @field_validator('event_type')
    @classmethod
    def type_valid(cls, value):
        if value not in ('arrival', 'departure'):
            raise ValueError('Use arrival or departure')
        return value

    @field_validator('event_timestamp')
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('Timestamp must include a timezone offset')
        return value.astimezone(timezone.utc) if value else value


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()


def credential(user_id, password):
    salt = secrets.token_hex(16)
    return LocalCredential(user_id=user_id, salt=salt, password_hash=password_hash(password, salt))


def create_local_app(db_path=None, origin=None, frontend_directory=None):
    """Factory parameters are operator inputs; clients cannot select a DB path."""
    origin = origin or os.environ.get('MEDFLOW_LOCAL_ORIGIN', 'http://127.0.0.1:8000')
    if urlsplit(origin).hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('Single-computer mode accepts loopback origins only')
    project = Path(__file__).resolve().parents[2]
    path = Path(db_path or os.environ.get('MEDFLOW_LOCAL_DB') or project / 'data' / 'medflow.sqlite3').resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine = create_engine('sqlite:///' + str(path), connect_args={'check_same_thread': False, 'timeout': 10})

    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=10000')
        connection.execute('PRAGMA journal_mode=WAL')

    Base.metadata.create_all(engine)
    LocalBase.metadata.create_all(engine)
    path.chmod(0o600)
    # SQLite equivalent of the PostgreSQL overlap exclusion constraint.
    with engine.begin() as connection:
        for operation in ('INSERT', 'UPDATE'):
            connection.exec_driver_sql(f"""
                CREATE TRIGGER IF NOT EXISTS attendance_no_overlap_{operation.lower()}
                BEFORE {operation} ON attendance_sessions
                WHEN (NEW.ended_at IS NULL OR NEW.ended_at > NEW.started_at)
                AND EXISTS (
                    SELECT 1 FROM attendance_sessions s
                    WHERE s.organization_id=NEW.organization_id AND s.doctor_id=NEW.doctor_id
                    AND s.id<>NEW.id AND (s.ended_at IS NULL OR s.ended_at>s.started_at)
                    AND s.started_at<COALESCE(NEW.ended_at,'9999-12-31')
                    AND COALESCE(s.ended_at,'9999-12-31')>NEW.started_at
                )
                BEGIN SELECT RAISE(ABORT,'overlapping attendance period'); END
            """)
    LocalDB = sessionmaker(engine, expire_on_commit=False)
    app = FastAPI(title='Medflow — Single Computer', version='1.1.0')
    app.state.db_path = path
    app.state.engine = engine
    buckets = defaultdict(deque)

    @app.middleware('http')
    async def local_boundary(request, call_next):
        if request.client and request.client.host not in ('127.0.0.1', '::1'):
            return JSONResponse({'detail': 'Localhost access only'}, 403)
        if request.headers.get('host') != urlsplit(origin).netloc:
            return JSONResponse({'detail': 'Invalid local host'}, 403)
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            if request.headers.get('origin') != origin or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Invalid request origin'}, 403)
            if int(request.headers.get('content-length', '0')) > 1024 * 1024:
                return JSONResponse({'detail': 'Request too large'}, 413)
        if request.url.path.startswith('/api/'):
            # Bound in memory: this process serves one loopback computer only.
            key = 'login' if request.url.path == '/api/local/login' else 'api'
            bucket = buckets[key]
            window = 60 if key == 'api' else 300
            limit = 300 if key == 'api' else 20
            stamp = time.monotonic()
            while bucket and bucket[0] < stamp-window:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse({'detail': 'Too many attempts; try again shortly'}, 429)
            bucket.append(stamp)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin', 'X-Frame-Options': 'DENY'})
        return response

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse({'detail': 'Duplicate account, timestamp, or overlapping attendance period'}, 409)

    @app.exception_handler(OperationalError)
    async def database_busy(request, exc):
        return JSONResponse({'detail': 'The local database is busy. Retry this request.'}, 503)

    def local_principal(request: Request):
        raw = request.cookies.get('medflow_session', '')
        if not raw:
            raise HTTPException(401, 'Sign in at /local')
        with LocalDB() as db:
            row = db.execute(select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(AuthSession.token_hash == token_hash(raw))).first()
            if not row or row[0].expires_at <= now() or row[1].status != 'active':
                raise HTTPException(401, 'Your local session expired or account is disabled')
            user = row[1]
            return Principal(user.id, user.organization_id, user.role)

    def local_database(p=Depends(local_principal)):
        with LocalDB() as db:
            # Single-machine writes serialize before reading, including check-in races.
            db.execute(text('BEGIN IMMEDIATE'))
            yield db
            db.commit()

    def local_guard(request: Request):
        # Loopback/Host/Origin enforcement is handled for every route above.
        pass

    app.dependency_overrides[principal] = local_principal
    app.dependency_overrides[database] = local_database
    app.dependency_overrides[guard_mutation] = local_guard

    @app.get('/api/local/status')
    def status():
        with LocalDB() as db:
            return {'mode': 'local', 'setup_required': db.scalar(select(LocalCredential.user_id).limit(1)) is None, 'full_dashboard_available': frontend.is_dir()}

    @app.post('/api/local/setup', status_code=201)
    def setup(body: Setup):
        with LocalDB() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            if db.scalar(select(LocalCredential.user_id).limit(1)):
                raise HTTPException(409, 'This computer is already configured')
            if body.admin_email.casefold() == body.doctor_email.casefold():
                raise HTTPException(422, 'Administrator and doctor need separate emails')
            org = Organization(name=body.organization, settings={'reporting_timezone': body.timezone, 'doctor_exports_enabled': True})
            db.add(org); db.flush()
            department = Department(organization_id=org.id, name='General'); db.add(department); db.flush()
            admin_user = User(organization_id=org.id, full_name=body.admin_name, email=body.admin_email.casefold(), role='admin')
            doctor = User(organization_id=org.id, full_name=body.doctor_name, email=body.doctor_email.casefold(), role='doctor', department_id=department.id)
            loc = Location(organization_id=org.id, name=body.location, building='Local facility', timezone=body.timezone)
            db.add_all([admin_user, doctor, loc]); db.flush()
            db.add_all([credential(admin_user.id, body.admin_password), credential(doctor.id, body.doctor_password)])
            db.add(AuditLog(organization_id=org.id, actor_id=admin_user.id, action='local:setup', resource_type='workspace'))
            db.commit()
            return {'status': 'ready', 'doctor_id': doctor.id, 'location_id': loc.id}

    @app.post('/api/local/login')
    def login(body: Login):
        with LocalDB() as db:
            row = db.execute(select(User, LocalCredential).join(LocalCredential, LocalCredential.user_id == User.id).where(User.email == body.email.casefold(), User.status == 'active')).first()
            # Perform the hash even for an unknown account to reduce timing differences.
            salt = row[1].salt if row else '00' * 16
            expected = row[1].password_hash if row else '00' * 32
            valid = secrets.compare_digest(password_hash(body.password, salt), expected)
            if not row or not valid:
                raise HTTPException(401, 'Email or password is incorrect')
            raw = secrets.token_urlsafe(48)
            db.add(AuthSession(token_hash=token_hash(raw), user_id=row[0].id, expires_at=now()+timedelta(hours=8)))
            db.add(AuditLog(organization_id=row[0].organization_id, actor_id=row[0].id, action='local:login', resource_type='auth_session'))
            db.commit()
        response = JSONResponse({'status': 'signed_in'})
        response.set_cookie('medflow_session', raw, httponly=True, secure=False, samesite='strict', max_age=8*3600)
        return response

    @app.post('/api/local/logout')
    @app.post('/api/auth/logout')
    def logout(request: Request, p=Depends(local_principal), db=Depends(local_database)):
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(request.cookies.get('medflow_session', ''))))
        if session:
            db.delete(session)
        audit(db, p, 'local:logout', 'auth_session')
        response = JSONResponse({'status': 'signed_out'})
        response.delete_cookie('medflow_session')
        return response

    @app.post('/api/local/accounts', status_code=201)
    def add_account(body: LocalAccount, p=Depends(local_principal), db=Depends(local_database)):
        if p.role != 'admin':
            raise HTTPException(403, 'Administrator permission required')
        department = db.scalar(scope(Department, p).where(Department.name == body.department))
        if not department:
            department = Department(organization_id=p.organization_id, name=body.department)
            db.add(department); db.flush()
        user = User(organization_id=p.organization_id, full_name=body.full_name, email=body.email.casefold(), role='doctor', department_id=department.id)
        db.add(user); db.flush()
        db.add(credential(user.id, body.password))
        audit(db, p, 'create', 'local_account', user.id)
        result = {'id': user.id, 'full_name': user.full_name, 'email': user.email, 'role': 'doctor'}
        db.commit()
        return result

    @app.get('/api/auth/login')
    def login_page():
        return RedirectResponse('/local')

    @app.get('/api/dashboard')
    def local_dashboard(date: date | None = None, period: str = 'This week', p=Depends(local_principal), db=Depends(local_database)):
        stamp = now()
        opened = db.scalars(scope(AttendanceSession, p).where(AttendanceSession.source == 'manual', AttendanceSession.ended_at.is_(None))).all()
        for session in opened:
            session.duration_seconds = max(0, int((stamp-session.started_at).total_seconds()))
        db.flush()
        result = dashboard(db, p, date, period)
        active = {s.doctor_id: s for s in opened}
        location_names = {loc['id']: loc['name'] for loc in result['locations']}
        for doctor in result['doctors']:
            session = active.get(doctor['id'])
            doctor['status'] = 'Manual check-in' if session else 'Absent'
            doctor['location_id'] = session.location_id if session else None
            doctor['location'] = location_names.get(session.location_id) if session else None
            doctor['last_seen'] = session.started_at if session else None
        result['mode'] = 'local'
        result['organization_name'] = db.get(Organization, p.organization_id).name
        result['metrics']['present'] = len(active)
        for loc in result['locations']:
            loc['count'] = sum(s.location_id == loc['id'] for s in opened)
        audit(db, p, 'read', 'dashboard')
        return result

    def timestamp_data(row, session):
        return {'id': row.id, 'doctor_id': row.doctor_id, 'location_id': row.location_id, 'session_id': row.session_id, 'event_type': row.event_type, 'event_timestamp': row.event_timestamp, 'received_timestamp': row.received_timestamp, 'source_event_id': row.source_event_id, 'duration_seconds': session.duration_seconds if session else row.duration_seconds, 'confidence_status': 'unverified', 'source': 'manual'}

    @app.post('/api/local/timestamps', status_code=201)
    def timestamp(body: TimestampInput, p=Depends(local_principal), db=Depends(local_database)):
        doctor_id = body.doctor_id or p.id
        if p.role != 'admin' and doctor_id != p.id:
            raise HTTPException(403, 'You can only record your own timestamps')
        doctor = get_record(db, User, doctor_id, p)
        if doctor.role != 'doctor' or doctor.status != 'active':
            raise HTTPException(422, 'Select an active doctor account')
        loc = get_record(db, Location, body.location_id, p)
        if not loc.active:
            raise HTTPException(422, 'Location is disabled')
        received = now()
        stamp = body.event_timestamp or received
        if stamp > received+timedelta(seconds=30) or stamp < received-timedelta(days=30):
            raise HTTPException(422, 'Timestamp must be within the previous 30 days and cannot be in the future')
        existing = db.scalar(select(LocalTimestamp).where(LocalTimestamp.organization_id == p.organization_id, LocalTimestamp.source_event_id == body.source_event_id))
        if existing:
            if (existing.doctor_id, existing.location_id, existing.event_type) != (doctor_id, loc.id, body.event_type) or (body.event_timestamp is not None and existing.event_timestamp != stamp):
                raise HTTPException(409, 'This event ID was already used for a different timestamp')
            return {**timestamp_data(existing, db.get(AttendanceSession, existing.session_id)), 'duplicate': True}
        opened = db.scalar(scope(AttendanceSession, p).where(AttendanceSession.doctor_id == doctor_id, AttendanceSession.ended_at.is_(None)))
        if body.event_type == 'arrival':
            if opened:
                raise HTTPException(409, 'Already checked in. Record departure before another arrival.')
            if db.scalar(scope(AttendanceSession, p).where(AttendanceSession.doctor_id == doctor_id, AttendanceSession.ended_at > stamp)):
                raise HTTPException(409, 'Arrival overlaps a previously recorded attendance period')
            session = AttendanceSession(organization_id=p.organization_id, doctor_id=doctor_id, location_id=loc.id, started_at=stamp, duration_seconds=0, confidence_status='unverified', source='manual', session_status='open')
            db.add(session); db.flush()
        else:
            if not opened:
                raise HTTPException(409, 'No arrival recorded. Record an arrival first.')
            if opened.location_id != loc.id:
                raise HTTPException(409, 'Departure must match the location of the open arrival')
            if stamp < opened.started_at:
                raise HTTPException(422, 'Departure cannot be earlier than arrival')
            opened.ended_at = stamp
            opened.duration_seconds = int((stamp-opened.started_at).total_seconds())
            opened.session_status = 'closed'
            session = opened
        row = LocalTimestamp(organization_id=p.organization_id, doctor_id=doctor_id, location_id=loc.id, session_id=session.id, duration_seconds=session.duration_seconds, event_type=body.event_type, source_event_id=body.source_event_id, event_timestamp=stamp, received_timestamp=received, recorded_by=p.id)
        db.add(row); db.flush()
        audit(db, p, 'manual:'+body.event_type, 'timestamp', row.id)
        result = {**timestamp_data(row, session), 'duplicate': False}
        # Commit explicitly before returning success, including disk/constraint errors.
        db.commit()
        return result

    @app.get('/api/local/timestamps')
    def timestamp_history(p=Depends(local_principal), db=Depends(local_database)):
        q = select(LocalTimestamp).where(LocalTimestamp.organization_id == p.organization_id)
        if p.role != 'admin':
            q = q.where(LocalTimestamp.doctor_id == p.id)
        users = {u.id: u.full_name for u in db.scalars(scope(User, p))}
        locations = {l.id: l.name for l in db.scalars(scope(Location, p))}
        audit(db, p, 'read', 'timestamps')
        return [{**timestamp_data(row, db.get(AttendanceSession, row.session_id)), 'doctor_name': users.get(row.doctor_id), 'location': locations.get(row.location_id)} for row in db.scalars(q.order_by(LocalTimestamp.event_timestamp.desc()).limit(500))]

    from .schemas import CheckinInput

    @app.post('/api/checkin')
    def dashboard_checkin(body: CheckinInput, p=Depends(local_principal), db=Depends(local_database)):
        if p.role != 'doctor':
            raise HTTPException(403, 'Doctor account required')
        return timestamp(TimestampInput(event_type='arrival' if body.action == 'start' else 'departure', location_id=body.location_id), p, db)

    @app.get('/api/presence')
    def local_presence(p=Depends(local_principal), db=Depends(local_database)):
        data = local_dashboard(p=p, db=db)
        return {'doctors': data['doctors'], 'observed_at': data['updated_at'], 'source': 'manual'}

    @app.get('/health/ready')
    def ready():
        with LocalDB() as db:
            db.execute(text('SELECT 1'))
        return {'status': 'ready', 'storage': 'sqlite', 'mode': 'local'}

    # Reuse protected reports, corrections, profiles, exports and administration.
    # The production server has no local login, setup or timestamp endpoints.
    from .main import app as production_app
    excluded = {'/api/dashboard', '/api/events', '/api/presence', '/api/checkin'}
    inherited = APIRouter()
    inherited.routes = [route for route in production_app.routes if isinstance(route, APIRoute) and route.path.startswith('/api/') and not route.path.startswith(('/api/auth/', '/api/integrations/')) and route.path not in excluded]
    app.include_router(inherited)

    @app.get('/local', response_class=HTMLResponse)
    def console():
        return (Path(__file__).with_name('local.html')).read_text()

    frontend = Path(frontend_directory or project / 'out')
    if frontend.is_dir():
        @app.get('/')
        def index(request: Request):
            try:
                local_principal(request)
            except HTTPException:
                return RedirectResponse('/local')
            return FileResponse(frontend / 'index.html')
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    else:
        @app.get('/')
        def index():
            return RedirectResponse('/local')
    return app
