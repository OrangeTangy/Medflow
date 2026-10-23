from datetime import timedelta, timezone
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.android_wifi import parse_android_log
from app.local_models import LocalWifiEvent
from app.models import AttendanceSession, AuditLog, now
from test_local import local, login


def marker(kind='connected', at=None):
    return f'MEDFLOW|{kind}|{int((at or now()).timestamp()*1000)}'


def import_body(content=None):
    return {'device_id': str(uuid.uuid4()), 'content': content or marker()}


def test_android_markers_preserve_utc_and_ignore_unrelated_log_text():
    content = 'private unrelated text\nLog: MEDFLOW|disconnected|1792710005123\nLog: MEDFLOW|connected|1792710000123'
    rows = parse_android_log(content, str(uuid.uuid4()), 'account-one')
    assert [row['event_type'] for row in rows] == ['connected', 'disconnected']
    assert rows[0]['observed_at'].tzinfo == timezone.utc
    assert rows[0]['observed_at'].microsecond == 123000
    assert (rows[1]['observed_at']-rows[0]['observed_at']).total_seconds() == 5
    assert 'private' not in str(rows)
    assert all(row['source'] == 'android_macrodroid_test' for row in rows)


def test_android_duplicates_are_stable_and_scoped_to_device_and_account():
    content, device = marker(), str(uuid.uuid4())
    first = parse_android_log(content+'\n'+content, device, 'account-one')
    assert len(first) == 1
    assert parse_android_log(content, device, 'account-one') == first
    assert parse_android_log(content, device, 'account-two')[0]['id'] != first[0]['id']
    assert parse_android_log(content, str(uuid.uuid4()), 'account-one')[0]['id'] != first[0]['id']


@pytest.mark.parametrize('content', ['', 'no markers', 'MEDFLOW|connected|{system_time_ms}', 'MEDFLOW|connected|17927100001234', 'MEDFLOW|arrival|1792710000123', marker()+'\nMEDFLOW|disconnected|bad'])
def test_android_malformed_logs_rejected(content):
    with pytest.raises(ValueError):
        parse_android_log(content, str(uuid.uuid4()), 'account-one')


def test_android_import_size_bounded():
    with pytest.raises(ValueError):
        parse_android_log((marker()+'\n')*1001, str(uuid.uuid4()), 'account-one')


def test_android_api_commits_phone_timestamps_once_without_creating_attendance(local):
    app, client, ids = local
    stamp = now()-timedelta(seconds=20)
    body = import_body(marker('connected', stamp)+'\n'+marker('disconnected', stamp+timedelta(seconds=10)))
    assert client.post('/api/local/wifi-events/import', json=body).status_code == 401
    login(client)
    result = client.post('/api/local/wifi-events/import', json=body)
    assert result.status_code == 200, result.text
    assert result.json() == {'inserted': 2, 'duplicates': 0, 'source': 'device_reported_test', 'attendance_modified': False}
    with Session(app.state.engine) as db:
        rows = db.scalars(select(LocalWifiEvent).order_by(LocalWifiEvent.observed_at)).all()
        assert len(rows) == 2
        assert rows[0].doctor_id == ids['doctor_id']
        assert rows[0].observed_at == stamp.replace(microsecond=stamp.microsecond//1000*1000)
        assert rows[0].received_at >= rows[0].observed_at
        assert db.scalar(select(AttendanceSession)) is None
        assert db.scalar(select(AuditLog).where(AuditLog.action == 'import_android_wifi')) is not None
    retry = client.post('/api/local/wifi-events/import', json=body)
    assert retry.json()['inserted'] == 0 and retry.json()['duplicates'] == 2
    assert len(client.get('/api/local/wifi-events').json()) == 2
    assert client.get('/api/attendance').json() == []


def test_android_batch_with_invalid_time_is_rejected_atomically(local):
    app, client, ids = local
    login(client)
    content = marker()+'\n'+marker('disconnected', now()-timedelta(days=31))
    result = client.post('/api/local/wifi-events/import', json=import_body(content))
    assert result.status_code == 422
    assert client.get('/api/local/wifi-events').json() == []


def test_android_api_blocks_admin_import_and_forged_identity(local):
    app, client, ids = local
    body = import_body()
    login(client, 'admin')
    assert client.post('/api/local/wifi-events/import', json=body).status_code == 403
    login(client)
    assert client.post('/api/local/wifi-events/import', json={**body, 'doctor_id': 'another-doctor'}).status_code == 422


def test_doctor_cannot_read_another_doctors_phone_log(local):
    app, client, ids = local
    login(client)
    assert client.post('/api/local/wifi-events/import', json=import_body()).status_code == 200
    login(client, 'admin')
    assert len(client.get('/api/local/wifi-events').json()) == 1
    result = client.post('/api/local/accounts', json={'full_name': 'Dr. Peer', 'email': 'peer@local.test', 'department': 'General', 'password': 'peer-test-password'})
    assert result.status_code == 201
    result = client.post('/api/local/login', json={'email': 'peer@local.test', 'password': 'peer-test-password'})
    assert result.status_code == 200
    assert client.get('/api/local/wifi-events').json() == []
