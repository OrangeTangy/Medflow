#!/usr/bin/env python3
"""Verify a local handoff using temporary storage and synthetic device events."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import uuid


def check(response, expected, stage):
    if response.status_code != expected:
        raise RuntimeError(f'{stage}: expected HTTP {expected}, got {response.status_code}')
    return response.json()


def main():
    project = Path(__file__).resolve().parents[1]
    environment = project / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if Path(sys.prefix).resolve() != environment.resolve() and python.is_file():
        return subprocess.call([str(python), str(Path(__file__).resolve())], cwd=project)
    if sys.version_info < (3, 12):
        print('FAIL: Python 3.12+ is required.', file=sys.stderr)
        return 1
    if not python.is_file():
        print('Run python scripts/run_local.py once to install .venv, stop it, then rerun this check.', file=sys.stderr)
        return 1
    sys.path.insert(0, str(project / 'backend'))
    origin = 'http://127.0.0.1:8000'
    with TemporaryDirectory(prefix='medflow handoff ') as folder:
        path = Path(folder) / 'synthetic.sqlite3'
        url = 'sqlite:///' + str(path)
        # Configure SQLite before importing modules: no PostgreSQL driver or
        # cloud provider is needed, and the real database is never opened.
        os.environ.update(DATABASE_URL=url, AUTH_DATABASE_URL=url,
                          WORKER_DATABASE_URL=url, TRANSCRIPTION_APPROVED='false',
                          SUMMARY_APPROVED='false')
        from fastapi.testclient import TestClient
        from zoneinfo import ZoneInfo
        from app.local import create_local_app
        from app.device_receiver import create_receiver

        assert datetime(2026, 1, 1, tzinfo=ZoneInfo('Asia/Kolkata')).utcoffset() == timedelta(hours=5, minutes=30)
        app = create_local_app(path, origin=origin, frontend_directory=Path(folder)/'no-frontend-build')
        restarted = None
        setup = {
            'organization': 'Synthetic handoff check',
            'admin_name': 'Test Administrator',
            'admin_email': 'admin@handoff.test',
            'admin_password': secrets.token_urlsafe(24),
            'doctor_name': 'Test Doctor',
            'doctor_email': 'doctor@handoff.test',
            'doctor_password': secrets.token_urlsafe(24),
            'location': 'Test facility',
            'timezone': 'Asia/Kolkata',
        }

        def connect(application):
            return TestClient(application, base_url=origin, client=('127.0.0.1', 50000), headers={'Origin': origin})

        def login(client, role='doctor'):
            check(client.post('/api/local/login', json={
                'email': setup[role+'_email'], 'password': setup[role+'_password'],
            }), 200, 'Local sign-in')

        try:
            with connect(app) as web:
                assert web.get('/local').status_code == 200
                ids = check(web.post('/api/local/setup', json=setup), 201, 'Fresh setup')
                login(web)
                assert web.get('/api/users').status_code == 403
                start = datetime.now(timezone.utc)-timedelta(minutes=30)
                for kind, stamp in [('arrival', start), ('departure', start+timedelta(minutes=25))]:
                    saved = check(web.post('/api/local/timestamps', json={
                        'event_type': kind, 'location_id': ids['location_id'],
                        'event_timestamp': stamp.isoformat(), 'source_event_id': str(uuid.uuid4()),
                    }), 201, 'Timestamp commit')
                assert saved['duration_seconds'] == 1500
                check(web.post('/api/reports', json={
                    'original_transcript': 'Synthetic operational meeting.',
                    'edited_transcript': 'Synthetic operational meeting.',
                    'category': 'Meetings', 'location_id': ids['location_id'],
                }), 201, 'Activity save')
                print('PASS: fresh setup, doctor permissions, timezone, timestamps, duration, activity')

                pairing = check(web.post('/api/local/devices', json={
                    'name': 'Synthetic collector', 'target_ssid': 'ReplicationTestWiFi',
                    'receiver_url': 'http://192.168.1.10:8765',
                }), 201, 'Pairing')['pairing']
                with TestClient(create_receiver(app.state.engine), base_url='http://192.168.1.10:8765',
                                client=('192.168.1.20', 50001),
                                headers={'Authorization': 'Bearer '+pairing['token']}) as device:
                    for kind in ['connected', 'disconnected']:
                        event = {'id': str(uuid.uuid4()), 'event_type': kind,
                                 'observed_at': datetime.now(timezone.utc).isoformat(),
                                 'ssid': pairing['ssid']}
                        check(device.post('/api/events', json=event), 200, 'Paired event')
                    assert check(device.post('/api/events', json=event), 200, 'Retry')['duplicate']
                    notices = check(web.get('/api/local/notifications?after=0'), 200, 'Notifications')
                    assert len(notices) == 2
                    attendance = check(web.get('/api/attendance'), 200, 'Attendance scope')
                    assert len(attendance) == 1 and attendance[0]['duration_seconds'] == 1500
                    check(web.post('/api/local/devices/'+pairing['device_id']+'/revoke'), 200, 'Revocation')
                    event['id'] = str(uuid.uuid4())
                    assert device.post('/api/events', json=event).status_code == 401
                login(web, 'admin')
                assert web.get('/api/users').status_code == 200
                assert len(check(web.get('/api/local/notifications'), 200, 'Admin review')) == 2
                print('PASS: paired notifications, retry deduplication, revocation, admin review')

            restarted = create_local_app(path, origin=origin, frontend_directory=Path(folder)/'no-frontend-build')
            with connect(restarted) as web:
                login(web)
                assert not check(web.get('/api/local/status'), 200, 'Restart status')['setup_required']
                assert len(check(web.get('/api/local/timestamps'), 200, 'Restart timestamps')) == 2
                assert len(check(web.get('/api/reports'), 200, 'Restart reports')) == 1
                assert len(check(web.get('/api/local/notifications'), 200, 'Restart notifications')) == 2
            backup = Path(folder)/'backup.sqlite3'
            subprocess.run([sys.executable, str(project/'scripts/run_local.py'),
                            '--database', str(path), '--backup', str(backup)],
                           check=True, stdout=subprocess.DEVNULL)
            connection = sqlite3.connect(backup)
            try:
                assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert connection.execute('SELECT count(*) FROM local_timestamps').fetchone()[0] == 2
                assert connection.execute('SELECT count(*) FROM local_notifications').fetchone()[0] == 2
            finally:
                connection.close()
            print('PASS: restart persistence and consistent SQLite backup')
        finally:
            if restarted is not None:
                restarted.state.engine.dispose()
            app.state.engine.dispose()
    print('Local handoff check passed. Physical WiFi and production integrations still require site testing.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
