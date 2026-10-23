import json
import uuid
import pytest
from wifi_probe import Connection, Snapshot, ProbeError, linux_snapshot, mac_snapshot, split_nmcli
from watch_wifi import EventLog, Tracker
from test_local import local, login
from app.models import now


def events(log):
    return [json.loads(row[0]) for row in log.connection.execute('SELECT payload FROM wifi_events ORDER BY rowid')]


def test_nmcli_escaped_network_names():
    assert split_nmcli(r'*:My\:Network\\Name') == ['*', 'My:Network\\Name']


def test_linux_reads_association_without_internet_probe():
    calls = []
    def run(args):
        calls.append(args)
        return 'wlan0:wifi:connected\neth0:ethernet:connected' if 'status' in args else r'*:My\:WiFi'
    result = linux_snapshot(run)
    assert result.connections == (Connection('wlan0', 'My:WiFi'),)
    assert '--rescan' in calls[1] and 'no' in calls[1]


def test_linux_wifi_radio_off_is_disconnected():
    assert linux_snapshot(lambda args: 'wlan0:wifi:unavailable').connections == ()


def test_no_wifi_adapter_is_unknown_not_disconnected():
    with pytest.raises(ProbeError):
        linux_snapshot(lambda args: 'eth0:ethernet:connected')


def test_mac_connected_and_disconnected():
    def run(args):
        if '-listallhardwareports' in args:
            return 'Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: unused\n\nHardware Port: Ethernet\nDevice: en1'
        if '/sbin/ifconfig' in args:
            return 'en0: flags=8863\n\tstatus: active\n'
        return 'Current Wi-Fi Network: Home WiFi\n'
    assert mac_snapshot(run).connections == (Connection('en0', 'Home WiFi'),)
    def disconnected(args):
        return 'Hardware Port: Wi-Fi\nDevice: en0\n' if '-listallhardwareports' in args else '\tstatus: inactive\n'
    assert mac_snapshot(disconnected).connections == ()


def test_mac_redacted_ssid_does_not_invent_disconnect():
    def run(args):
        if '-listallhardwareports' in args:
            return 'Hardware Port: Wi-Fi\nDevice: en0\n'
        if '/sbin/ifconfig' in args:
            return '\tstatus: active\n'
        return 'You are not associated with an AirPort network.\n'
    assert mac_snapshot(run).connections == (Connection('en0', None),)


def test_transitions_persist_offline_and_do_not_repeat_unchanged_state(tmp_path):
    log = EventLog(tmp_path)
    tracker = Tracker(log)
    tracker.update(Snapshot((Connection('en0', 'Home'),), 1))
    tracker.update(Snapshot((Connection('en0', 'Home'),), 1))
    tracker.update(Snapshot((), 1))
    tracker.update(Snapshot((Connection('en0', 'Home'),), 1))
    assert [e['event_type'] for e in events(log)] == ['connected', 'disconnected', 'connected']
    assert len((tmp_path/'wifi-events.jsonl').read_text().splitlines()) == 3
    assert events(log)[0]['initial_observation'] is True
    log.close()
    reopened = EventLog(tmp_path)
    assert len(events(reopened)) == 3
    reopened.close()


def test_probe_failure_never_becomes_false_departure(tmp_path):
    log = EventLog(tmp_path)
    tracker = Tracker(log)
    tracker.update(Snapshot((Connection('en0', 'Home'),), 1))
    tracker.probe_error(ProbeError('Permission denied'))
    tracker.probe_error(ProbeError('Permission denied'))
    tracker.update(Snapshot((Connection('en0', 'Home'),), 1))
    assert [e['event_type'] for e in events(log)] == ['connected', 'probe_error', 'probe_recovered']
    log.close()


def test_switching_wifi_has_explicit_network_change(tmp_path):
    log = EventLog(tmp_path)
    tracker = Tracker(log)
    tracker.update(Snapshot((Connection('en0', 'Home'),), 1))
    tracker.update(Snapshot((Connection('en0', 'Office'),), 1))
    assert events(log)[1]['event_type'] == 'network_changed'
    assert events(log)[1]['previous_ssid'] == 'Home'
    log.close()


def test_pending_sync_is_bound_to_authenticated_account(tmp_path):
    log = EventLog(tmp_path)
    Tracker(log, 'doctor-one').emit('connected', interface='en0', ssid='Home')
    assert len(log.pending('doctor-one')) == 1
    assert log.pending('doctor-two') == []
    log.close()


def observation():
    return {'id': str(uuid.uuid4()), 'run_id': str(uuid.uuid4()), 'device_id': str(uuid.uuid4()), 'observed_at': now().isoformat(), 'event_type': 'connected', 'source': 'local_wifi_test', 'interface': 'en0', 'ssid': 'Test Network'}


def test_wifi_api_is_authenticated_idempotent_and_does_not_claim_attendance(local):
    app, client, ids = local
    body = observation()
    assert client.post('/api/local/wifi-events', json=body).status_code == 401
    login(client)
    assert client.post('/api/local/wifi-events', json=body).status_code == 201
    retry = client.post('/api/local/wifi-events', json=body)
    assert retry.json()['duplicate']
    history = client.get('/api/local/wifi-events').json()
    assert len(history) == 1 and history[0]['evidence'] == 'device_reported_test'
    assert client.get('/api/attendance').json() == []


def test_wifi_api_does_not_accept_forged_doctor_id(local):
    app, client, ids = local
    login(client)
    assert client.post('/api/local/wifi-events', json={**observation(), 'doctor_id': 'peer'}).status_code == 422
