#!/usr/bin/env python3
"""Run the main attendance functions on Windows/macOS/Linux with Python 3.12+."""
import argparse
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description='Run Medflow locally with a persistent SQLite database.')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--database', type=Path, help='SQLite file path; defaults to data/medflow.sqlite3')
    parser.add_argument('--backup', type=Path, help='Back up the database and exit')
    parser.add_argument('--no-install', action='store_true', help='Use the existing project virtual environment')
    parser.add_argument('--receive-devices', action='store_true', help='Also start the paired WiFi receiver on a separate port')
    parser.add_argument('--receiver-host', default='0.0.0.0')
    parser.add_argument('--receiver-port', type=int, default=8765)
    parser.add_argument('--tls-cert', type=Path)
    parser.add_argument('--tls-key', type=Path)
    parser.add_argument('--insecure-lan', action='store_true', help='Explicitly allow unencrypted receiver HTTP for a private LAN test')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    database = (args.database or project / 'data' / 'medflow.sqlite3').resolve()
    if args.backup:
        if not database.is_file():
            parser.error('Database does not exist yet. Start the app and create a workspace first.')
        destination = args.backup.resolve()
        if destination == database or destination.exists():
            parser.error('Choose a new backup file path')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        destination.chmod(0o600)
        print('Database backup saved:', destination)
        return 0
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    if args.receive_devices:
        if not 1024 <= args.receiver_port <= 65535 or args.receiver_port == args.port:
            parser.error('Choose a separate receiver port between 1024 and 65535')
        if bool(args.tls_cert) != bool(args.tls_key):
            parser.error('Provide both --tls-cert and --tls-key')
        if not args.tls_cert and not args.insecure_lan:
            parser.error('The receiver requires TLS. Use --tls-cert and --tls-key, or --insecure-lan for a private LAN test.')
        if args.tls_cert and (not args.tls_cert.is_file() or not args.tls_key.is_file()):
            parser.error('TLS certificate/key files were not found')
    environment = project / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    requirements = project / 'backend' / 'requirements-local.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / 'medflow-local-requirements.sha256'
    if not python.is_file():
        if args.no_install:
            parser.error('No virtual environment found. Run without --no-install the first time.')
        print('Creating the local Python environment…', flush=True)
        venv.create(environment, with_pip=True)
    if not args.no_install and (not marker.exists() or marker.read_text() != fingerprint):
        print('Installing local application dependencies…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        marker.write_text(fingerprint)
    origin = f'http://127.0.0.1:{args.port}'
    env = os.environ.copy()
    env.update(DATABASE_URL='sqlite:///' + str(database), AUTH_DATABASE_URL='sqlite:///' + str(database), MEDFLOW_LOCAL_DB=str(database), MEDFLOW_LOCAL_ORIGIN=origin, TRANSCRIPTION_APPROVED='false', SUMMARY_APPROVED='false', PYTHONDONTWRITEBYTECODE='1')
    print(f'\nMedflow is starting at {origin}/local', flush=True)
    print(f'Database: {database}\nOpen the URL in your browser. Press Ctrl+C to stop.\n', flush=True)
    receiver = None
    try:
        if args.receive_devices:
            # Avoid two first-run processes racing to create the SQLite schema.
            subprocess.run([str(python), '-c', 'import sys;sys.path.insert(0,sys.argv[1]);from app.local import create_local_app;app=create_local_app();app.state.engine.dispose()', str(project / 'backend')], cwd=project, env=env, check=True)
            command = [str(python), '-m', 'uvicorn', 'app.device_receiver:create_app', '--factory', '--app-dir', str(project / 'backend'), '--host', args.receiver_host, '--port', str(args.receiver_port), '--no-proxy-headers', '--no-access-log']
            if args.tls_cert:
                command.extend(['--ssl-certfile', str(args.tls_cert.resolve()), '--ssl-keyfile', str(args.tls_key.resolve())])
            else:
                print('LAN TEST: receiver traffic is unencrypted. Use a trusted private network only; do not forward this port to the Internet.', flush=True)
            receiver = subprocess.Popen(command, cwd=project, env=env)
            print(f'Paired device receiver on port {args.receiver_port}. The account/dashboard stays localhost-only.', flush=True)
        return subprocess.call([str(python), '-m', 'uvicorn', 'app.local:create_local_app', '--factory', '--app-dir', str(project / 'backend'), '--host', '127.0.0.1', '--port', str(args.port)], cwd=project, env=env)
    except KeyboardInterrupt:
        return 0
    finally:
        if receiver and receiver.poll() is None:
            receiver.terminate()
            try:
                receiver.wait(timeout=5)
            except subprocess.TimeoutExpired:
                receiver.kill()
                receiver.wait()


if __name__ == '__main__':
    raise SystemExit(main())
