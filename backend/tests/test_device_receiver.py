from datetime import timedelta
import json
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.device_receiver import create_receiver
from app.local_models import LocalNotification, LocalPairedDevice, LocalWifiEvent
from app.models import AttendanceSession, now
from app.wifi_pairing import validate_receiver_url
from test_local import local, login
from wifi_probe import Connection, Snapshot
from watch_wifi import EventLog, Tracker, PairedSyncClient


def pair(client, **overrides):
    result = client.post('/api/local/devices', json={'name':'Test Android','target_ssid':'My WiFi','receiver_url':'http://192.168.1.10:8765', **overrides})
    assert result.status_code == 201, result.text
    return result.json()['pairing']


def event(**overrides):
    return {'id':str(uuid.uuid4()),'event_type':'connected','observed_at':now().isoformat(),'ssid':'My WiFi', **overrides}


def receiver(local, pairing):
    app, _, _ = local
    return TestClient(create_receiver(app.state.engine), headers={'Authorization':'Bearer '+pairing['token']}, client=('192.168.1.20',4000))


def test_receiver_commits_event_and_notification_before_ack_and_deduplicates(local):
    app, client, ids = local
    login(client)
    config = pair(client)
    body = event()
    with receiver(local, config) as phone:
        response = phone.post('/api/events', json=body)
        assert response.status_code == 200, response.text
        assert response.json()['attendance_modified'] is False
        assert phone.post('/api/events', json=body).json()['duplicate']
    with Session(app.state.engine) as db:
        assert len(db.scalars(select(LocalWifiEvent)).all()) == 1
        notifications = db.scalars(select(LocalNotification)).all()
        assert len(notifications) == 1 and notifications[0].doctor_id == ids['doctor_id']
        assert db.scalar(select(AttendanceSession)) is None
        device = db.get(LocalPairedDevice,config['device_id'])
        assert config['token'] != device.token_hash
        assert device.last_state == 'connected'
    received = client.get('/api/local/notifications?after=0').json()
    assert len(received) == 1
    assert received[0]['evidence'] == 'device_reported_test'
    assert client.get('/api/local/notifications?after='+str(received[0]['id'])).json() == []


def test_revoked_pairing_cannot_send(local):
    _, client, _ = local
    login(client)
    config = pair(client)
    assert client.post('/api/local/devices/'+config['device_id']+'/revoke').status_code == 200
    with receiver(local,config) as phone:
        assert phone.post('/api/events',json=event()).status_code == 401


def test_receiver_rejects_forged_identity_and_wrong_wifi(local):
    _, client, _ = local
    login(client)
    config = pair(client)
    with receiver(local,config) as phone:
        assert phone.post('/api/events',json=event(doctor_id='peer')).status_code == 422
        assert phone.post('/api/events',json=event(ssid='Other WiFi')).status_code == 422
        assert phone.post('/api/events',json=event(),headers={'Authorization':'Bearer wrong'}).status_code == 401
        assert phone.post('/api/events',json=event(),headers={'Origin':'https://untrusted.example'}).status_code == 403
        assert phone.post('/api/events',content='x'*9000).status_code == 413
        assert phone.get('/api/local/devices').status_code == 404
        assert phone.get('/docs').status_code == 404


def test_queued_disconnect_preserves_phone_time_and_does_not_overwrite_newer_state(local):
    app, client, _ = local
    login(client)
    config = pair(client)
    with receiver(local,config) as phone:
        assert phone.post('/api/events',json=event()).status_code == 200
        old = event(event_type='disconnected', observed_at=(now()-timedelta(minutes=15)).isoformat())
        response = phone.post('/api/events',json=old)
        assert response.status_code == 200
    with Session(app.state.engine) as db:
        assert db.get(LocalPairedDevice,config['device_id']).last_state == 'connected'
    notifications = client.get('/api/local/notifications').json()
    assert len(notifications) == 2
    assert notifications[1]['observed_at'] != notifications[1]['received_at']


def test_conflicting_event_id_is_rejected(local):
    _, client, _ = local
    login(client)
    config = pair(client)
    body = event()
    with receiver(local,config) as phone:
        assert phone.post('/api/events',json=body).status_code == 200
        assert phone.post('/api/events',json={**body,'event_type':'disconnected'}).status_code == 409


def test_pair_and_notification_permissions(local):
    _, client, ids = local
    login(client)
    config = pair(client)
    with receiver(local,config) as phone:
        phone.post('/api/events',json=event())
    login(client,'admin')
    result = client.post('/api/local/accounts',json={'full_name':'Dr. Peer','email':'peer@local.test','department':'General','password':'peer-test-password'})
    assert result.status_code == 201
    peer = result.json()['id']
    assert len(client.get('/api/local/notifications').json()) == 1
    assert client.post('/api/local/login',json={'email':'peer@local.test','password':'peer-test-password'}).status_code == 200
    assert client.get('/api/local/devices').json() == []
    assert client.get('/api/local/notifications').json() == []
    assert client.post('/api/local/devices/'+config['device_id']+'/revoke').status_code == 404
    assert client.post('/api/local/devices',json={'name':'forged','target_ssid':'My WiFi','receiver_url':'http://192.168.1.10:8765','doctor_id':ids['doctor_id']}).status_code == 403


@pytest.mark.parametrize('url',['http://public.example','http://8.8.8.8:8765','https://user:password@example.com','https://example.com/api/events','file:///tmp/config','https://example.com:999999'])
def test_receiver_url_rejects_unsafe_or_ambiguous_configuration(url):
    with pytest.raises(ValueError):
        validate_receiver_url(url)


def test_target_network_transitions_and_redacted_name_do_not_invent_departure(tmp_path):
    log = EventLog(tmp_path)
    tracker = Tracker(log,target_ssid='My WiFi')
    tracker.update(Snapshot((Connection('wlan0','Other'),),1))
    tracker.update(Snapshot((Connection('wlan0','My WiFi'),),1))
    tracker.update(Snapshot((Connection('wlan0',None),),1))
    tracker.update(Snapshot((Connection('wlan0','My WiFi'),),1))
    tracker.update(Snapshot((Connection('wlan0','Other'),),1))
    rows=[json.loads(row[0]) for row in log.connection.execute('SELECT payload FROM wifi_events ORDER BY rowid')]
    assert [row['event_type'] for row in rows] == ['disconnected','connected','probe_error','probe_recovered','disconnected']
    log.close()


def test_paired_client_keeps_retry_payload_and_event_id(tmp_path):
    config={'version':1,'receiver_url':'https://receiver.example','token':'x'*43,'ssid':'My WiFi','device_id':str(uuid.uuid4())}
    path=tmp_path/'pairing.json'; path.write_text(json.dumps(config))
    client=PairedSyncClient(path)
    log=EventLog(tmp_path/'log')
    row=Tracker(log,actor_id=config['device_id']).emit('disconnected',interface='wlan0',ssid='My WiFi')
    class Transport:
        def __init__(self): self.requests=[]
        def open(self, request, timeout):
            self.requests.append(request)
            raise OSError('offline')
    transport=Transport(); client.client=transport
    for _ in range(2):
        with pytest.raises(OSError): client.flush(log)
    assert transport.requests[0].data == transport.requests[1].data
    assert json.loads(transport.requests[0].data)['id'] == row['id']
    assert len(log.pending(config['device_id'])) == 1
    log.close()


def test_rejected_event_is_retained_without_blocking_the_next_event(tmp_path):
    from urllib.error import HTTPError
    import io
    config={'version':1,'receiver_url':'https://receiver.example','token':'x'*43,'ssid':'My WiFi','device_id':str(uuid.uuid4())}
    path=tmp_path/'pairing.json'; path.write_text(json.dumps(config))
    client=PairedSyncClient(path)
    log=EventLog(tmp_path/'log')
    tracker=Tracker(log,actor_id=config['device_id'])
    invalid=tracker.emit('disconnected',ssid='My WiFi')
    valid=tracker.emit('connected',ssid='My WiFi')
    class Transport:
        def open(self,request,timeout):
            body=json.loads(request.data)
            if body['id'] == invalid['id']:
                raise HTTPError(request.full_url,422,'clock invalid',{},None)
            return io.BytesIO(json.dumps({'id':body['id']}).encode())
    client.client=Transport(); client.flush(log)
    rows=log.connection.execute('SELECT id,synced,sync_error FROM wifi_events ORDER BY rowid').fetchall()
    assert rows[0][0] == invalid['id'] and rows[0][1] == 2 and '422' in rows[0][2]
    assert rows[1][0] == valid['id'] and rows[1][1] == 1
    assert not log.pending(config['device_id'])
    log.close()
