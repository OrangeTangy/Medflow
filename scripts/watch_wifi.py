#!/usr/bin/env python3
"""Watch native WiFi association and durably log it even without Internet.

Python standard library only. Optional --sync sends authenticated computer-test
observations to the localhost Medflow app. No browser online/offline inference.
"""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import time
import uuid
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from wifi_probe import probe, ProbeError, Snapshot


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'wifi-events.sqlite3'
        self.connection = sqlite3.connect(self.path)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA busy_timeout=5000')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS wifi_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS wifi_events (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, observed_at TEXT NOT NULL,
                event_type TEXT NOT NULL, payload TEXT NOT NULL, actor_id TEXT,
                synced INTEGER NOT NULL DEFAULT 0
            );
        ''')
        self.connection.execute('INSERT OR IGNORE INTO wifi_settings (key,value) VALUES (?,?)', ('device_id', str(uuid.uuid4())))
        self.connection.commit()
        self.device_id = self.connection.execute('SELECT value FROM wifi_settings WHERE key=?', ('device_id',)).fetchone()[0]
        self.path.chmod(0o600)

    def append(self, payload, actor_id=None):
        encoded = json.dumps(payload, ensure_ascii=False)
        self.connection.execute('INSERT INTO wifi_events (id,run_id,observed_at,event_type,payload,actor_id) VALUES (?,?,?,?,?,?)', (payload['id'], payload['run_id'], payload['observed_at'], payload['event_type'], encoded, actor_id))
        self.connection.commit()  # Commit before printing or attempting any HTTP call.
        output = self.directory / 'wifi-events.jsonl'
        try:
            fd = os.open(output, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                stream.write(encoded+'\n')
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            print(f'JSON log unavailable ({type(exc).__name__}); the event is saved in SQLite.', file=sys.stderr)

    def pending(self, actor_id):
        return self.connection.execute('SELECT id,payload FROM wifi_events WHERE actor_id=? AND synced=0 ORDER BY rowid LIMIT 100', (actor_id,)).fetchall()

    def synced(self, event_id):
        self.connection.execute('UPDATE wifi_events SET synced=1 WHERE id=?', (event_id,))
        self.connection.commit()

    def close(self):
        self.connection.close()


class Tracker:
    def __init__(self, log, actor_id=None):
        self.log, self.actor_id = log, actor_id
        self.run_id = str(uuid.uuid4())
        self.previous = None
        self.error = None

    def emit(self, kind, **details):
        record = {'id': str(uuid.uuid4()), 'run_id': self.run_id, 'device_id': self.log.device_id, 'observed_at': utc_now(), 'event_type': kind, 'source': 'local_wifi_test', **details}
        self.log.append(record, self.actor_id)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        return record

    def update(self, snapshot):
        if self.error:
            self.emit('probe_recovered', note='WiFi observations are available again; the unobserved period remains unknown.')
            self.error = None
        current = {connection.interface: connection.ssid for connection in snapshot.connections}
        if self.previous is None:
            if current:
                for interface, ssid in current.items():
                    self.emit('connected', interface=interface, ssid=ssid, initial_observation=True)
            else:
                self.emit('disconnected', initial_observation=True, note='Disconnected at watcher start; no earlier departure time inferred.')
        else:
            for interface, ssid in self.previous.items():
                if interface not in current:
                    self.emit('disconnected', interface=interface, ssid=ssid, initial_observation=False)
                elif current[interface] != ssid:
                    self.emit('network_changed', interface=interface, previous_ssid=ssid, ssid=current[interface], initial_observation=False)
            for interface, ssid in current.items():
                if interface not in self.previous:
                    self.emit('connected', interface=interface, ssid=ssid, initial_observation=False)
        self.previous = current

    def probe_error(self, error):
        message = str(error)
        if self.error != message:
            self.emit('probe_error', diagnostic=message, note='Unknown WiFi state. No disconnection is inferred.')
            self.error = message


class SyncClient:
    def __init__(self, server, email=None, password=None):
        origin = server.rstrip('/')
        parts = urlsplit(origin)
        if parts.scheme != 'http' or parts.hostname != '127.0.0.1' or parts.username or parts.password or parts.path or parts.query or parts.fragment:
            raise ValueError('Use the localhost server URL, such as http://127.0.0.1:8000')
        self.origin = origin
        self.client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        self.call('/api/local/login', {'email': email or input('Local doctor account email: ').strip(), 'password': password or getpass.getpass('Local account password: ')})
        me = self.call('/api/me')
        if me['role'] != 'doctor':
            raise ValueError('Sign in with a local doctor account for this device test.')
        self.actor_id = me['id']

    def call(self, path, body=None):
        request = Request(self.origin+path, data=json.dumps(body).encode() if body is not None else None, headers={'Origin': self.origin, 'Content-Type': 'application/json'})
        with self.client.open(request, timeout=3) as response:
            return json.load(response)

    def flush(self, log):
        for event_id, payload in log.pending(self.actor_id):
            self.call('/api/local/wifi-events', json.loads(payload))
            log.synced(event_id)


def main():
    parser = argparse.ArgumentParser(description='Log WiFi connects/disconnects on this physical computer, including while offline.')
    parser.add_argument('--interval', type=float, default=2, help='Poll interval in seconds (default: 2)')
    parser.add_argument('--log-dir', type=Path, default=Path(__file__).resolve().parents[1]/'data')
    parser.add_argument('--sync', action='store_true', help='Also send the observations to your authenticated local doctor account')
    parser.add_argument('--server', default='http://127.0.0.1:8000')
    parser.add_argument('--once', action='store_true', help='Read/log the current WiFi state once, then exit')
    args = parser.parse_args()
    if not 0.5 <= args.interval <= 60:
        parser.error('Choose a polling interval between 0.5 and 60 seconds')
    sync = None
    if args.sync:
        try:
            sync = SyncClient(args.server)
        except (ValueError, HTTPError, URLError, OSError) as exc:
            print(f'Unable to sign in to the local app: {exc}. Start the app and use a doctor account, or omit --sync for local-only logs.', file=sys.stderr)
            return 1
    log = EventLog(args.log_dir)
    tracker = Tracker(log, sync.actor_id if sync else None)
    print(f'WiFi test log: {log.path}\nReadable log: {log.directory / "wifi-events.jsonl"}\nToggle WiFi off/on on THIS computer. Ctrl+C stops the watcher.\nDevice observations are not verified staff attendance.', file=sys.stderr, flush=True)
    tracker.emit('watcher_started', polling_seconds=args.interval)
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, stop)
    previous_tick = time.monotonic()
    sync_error = None
    try:
        while not stopping:
            tick = time.monotonic()
            if tick-previous_tick > max(15, args.interval*3):
                tracker.emit('monitor_gap', unobserved_seconds=round(tick-previous_tick, 1), note='The computer or watcher was suspended; connectivity during this gap is unknown.')
            previous_tick = tick
            try:
                tracker.update(probe())
            except ProbeError as exc:
                tracker.probe_error(exc)
            if sync:
                try:
                    sync.flush(log)
                    if sync_error:
                        print('Pending WiFi observations synced to the local app.', file=sys.stderr, flush=True)
                    sync_error = None
                except (HTTPError, URLError, OSError) as exc:
                    message = f'Local app sync unavailable ({type(exc).__name__}). Events remain saved on disk. If the session expired, restart --sync and sign in again.'
                    if sync_error != message:
                        print(message, file=sys.stderr, flush=True)
                    sync_error = message
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        tracker.emit('watcher_stopped', note='Watcher stopped. This does not imply WiFi disconnected.')
        if sync:
            try:
                sync.flush(log)
            except (HTTPError, URLError, OSError):
                pass
        log.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
