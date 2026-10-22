from datetime import timedelta, timezone
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.local import create_local_app
from app.local_models import LocalCredential, LocalTimestamp
from app.models import AttendanceSession, now

ORIGIN = 'http://127.0.0.1:8000'
SETUP = {'organization': 'Local Test Hospital', 'admin_name': 'Local Admin', 'admin_email': 'admin@local.test', 'admin_password': 'local-admin-test-password', 'doctor_name': 'Dr. Local Doctor', 'doctor_email': 'doctor@local.test', 'doctor_password': 'local-doctor-test-password', 'location': 'Main Hospital', 'timezone': 'UTC'}


def connect(app):
    return TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 50000), headers={'Origin': ORIGIN})


def login(client, role='doctor'):
    response = client.post('/api/local/login', json={'email': SETUP[role+'_email'], 'password': SETUP[role+'_password']})
    assert response.status_code == 200, response.text


@pytest.fixture
def local(tmp_path):
    path = tmp_path / 'attendance.sqlite3'
    app = create_local_app(path, origin=ORIGIN, frontend_directory=tmp_path / 'no-node-build')
    with connect(app) as client:
        response = client.post('/api/local/setup', json=SETUP)
        assert response.status_code == 201, response.text
        yield app, client, response.json()
    app.state.engine.dispose()


def record(client, ids, kind, stamp=None, key=None):
    body = {'event_type': kind, 'location_id': ids['location_id']}
    if stamp is not None:
        body['event_timestamp'] = stamp.isoformat() if hasattr(stamp, 'isoformat') else stamp
    if key:
        body['source_event_id'] = key
    return client.post('/api/local/timestamps', json=body)


def test_first_run_has_no_fake_attendance(local):
    app, client, ids = local
    login(client)
    data = client.get('/api/dashboard').json()
    assert data['mode'] == 'local' and data['sessions'] == []
    assert data['metrics']['hours'] == 0 and data['reports'] == []


def test_arrival_departure_are_committed_with_exact_duration(local):
    app, client, ids = local
    login(client)
    start = now()-timedelta(hours=2)
    arrival = record(client, ids, 'arrival', start, 'arrival-1')
    assert arrival.status_code == 201, arrival.text
    departure = record(client, ids, 'departure', start+timedelta(minutes=73), 'departure-1')
    assert departure.status_code == 201, departure.text
    assert departure.json()['duration_seconds'] == 4380
    with Session(app.state.engine) as db:
        rows = db.scalars(select(LocalTimestamp).order_by(LocalTimestamp.event_timestamp)).all()
        session = db.scalar(select(AttendanceSession))
        assert len(rows) == 2 and session.duration_seconds == 4380
        assert session.ended_at == start+timedelta(minutes=73)
        assert rows[0].event_timestamp == start
        assert rows[0].received_timestamp.tzinfo == timezone.utc
        assert session.confidence_status == 'unverified'


def test_duplicate_retry_does_not_insert_or_double_count(local):
    app, client, ids = local
    login(client)
    assert record(client, ids, 'arrival', key='same-event').status_code == 201
    repeated = record(client, ids, 'arrival', key='same-event')
    assert repeated.status_code == 201 and repeated.json()['duplicate']
    assert len(client.get('/api/local/timestamps').json()) == 1


def test_event_id_cannot_be_reused_for_different_payload(local):
    app, client, ids = local
    login(client)
    record(client, ids, 'arrival', key='shared')
    assert record(client, ids, 'departure', key='shared').status_code == 409


def test_departure_without_arrival_rejected(local):
    app, client, ids = local
    login(client)
    assert record(client, ids, 'departure').status_code == 409


def test_second_arrival_and_negative_duration_rejected(local):
    app, client, ids = local
    login(client)
    start = now()-timedelta(hours=1)
    record(client, ids, 'arrival', start)
    assert record(client, ids, 'arrival').status_code == 409
    assert record(client, ids, 'departure', start-timedelta(seconds=1)).status_code == 422


def test_timezone_less_and_future_timestamps_rejected(local):
    app, client, ids = local
    login(client)
    assert record(client, ids, 'arrival', '2026-10-22T08:00:00').status_code == 422
    assert record(client, ids, 'arrival', now()+timedelta(hours=1)).status_code == 422


def test_timezone_offset_round_trip(local):
    app, client, ids = local
    login(client)
    start = (now()-timedelta(hours=1)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    response = record(client, ids, 'arrival', start)
    assert response.status_code == 201
    from datetime import datetime
    assert datetime.fromisoformat(response.json()['event_timestamp']) == start


def test_doctor_cannot_record_for_other_doctor(local):
    app, client, ids = local
    login(client)
    assert client.post('/api/local/timestamps', json={'event_type': 'arrival', 'location_id': ids['location_id'], 'doctor_id': 'another-doctor'}).status_code == 403
    assert client.get('/api/users').status_code == 403


def test_admin_can_add_account_but_doctor_cannot(local):
    app, client, ids = local
    login(client, 'admin')
    body = {'full_name': 'Dr. Second', 'email': 'second@local.test', 'department': 'Cardiology', 'password': 'second-doctor-password'}
    result = client.post('/api/local/accounts', json=body)
    assert result.status_code == 201, result.text
    login(client)
    assert client.post('/api/local/accounts', json={**body, 'email': 'third@local.test'}).status_code == 403


def test_doctor_activity_saved_and_survives_server_restart(local):
    app, client, ids = local
    login(client)
    result = client.post('/api/reports', json={'original_transcript': 'Department meeting', 'edited_transcript': 'Attended the department meeting.', 'category': 'Meetings', 'location_id': ids['location_id']})
    assert result.status_code == 201, result.text
    record(client, ids, 'arrival')
    new_app = create_local_app(app.state.db_path, origin=ORIGIN)
    with connect(new_app) as restarted:
        login(restarted)
        assert len(restarted.get('/api/local/timestamps').json()) == 1
        reports = restarted.get('/api/reports').json()
        assert reports[0]['edited_transcript'] == 'Attended the department meeting.'
    new_app.state.engine.dispose()


def test_setup_cannot_reset_existing_workspace(local):
    app, client, ids = local
    assert client.post('/api/local/setup', json=SETUP).status_code == 409


def test_local_console_without_node_or_frontend_build(local):
    app, client, ids = local
    assert client.get('/local').status_code == 200
    assert 'Record arrival' in client.get('/local').text


def test_local_host_and_origin_guards(local):
    app, client, ids = local
    assert client.get('/api/local/status', headers={'Host': 'evil.test'}).status_code == 403
    assert client.post('/api/local/login', headers={'Origin': 'https://evil.test'}, json={}).status_code == 403
    with TestClient(app, base_url=ORIGIN, client=('192.168.1.5', 50000)) as remote:
        assert remote.get('/local').status_code == 403


def test_unauthenticated_and_logged_out_requests_rejected(local):
    app, client, ids = local
    assert client.get('/api/local/timestamps').status_code == 401
    login(client)
    assert client.post('/api/local/logout', json={}).status_code == 200
    assert record(client, ids, 'arrival').status_code == 401


def test_password_is_hashed_in_database(local):
    app, client, ids = local
    with Session(app.state.engine) as db:
        creds = db.scalars(select(LocalCredential)).all()
        assert len(creds) == 2
        assert all(c.password_hash not in (SETUP['admin_password'], SETUP['doctor_password']) for c in creds)
    connection = sqlite3.connect(app.state.db_path)
    assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    connection.close()


def test_concurrent_arrivals_create_one_session(local):
    from concurrent.futures import ThreadPoolExecutor
    app, client, ids = local
    login(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda n: record(client, ids, 'arrival', key='race-'+str(n)), [1, 2]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(client.get('/api/local/timestamps').json()) == 1


def test_doctor_does_not_see_peer_timestamp(local):
    app, client, ids = local
    login(client, 'admin')
    second = client.post('/api/local/accounts', json={'full_name': 'Dr. Peer', 'email': 'peer@local.test', 'department': 'General', 'password': 'peer-test-password'}).json()
    result = client.post('/api/local/timestamps', json={'doctor_id': second['id'], 'event_type': 'arrival', 'location_id': ids['location_id']})
    assert result.status_code == 201
    login(client)
    assert client.get('/api/local/timestamps').json() == []


def test_backup_preserves_committed_records(local, tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    app, client, ids = local
    login(client)
    record(client, ids, 'arrival')
    target = tmp_path / 'backup.sqlite3'
    project = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(project/'scripts/run_local.py'), '--database', str(app.state.db_path), '--backup', str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT count(*) FROM local_timestamps').fetchone()[0] == 1
