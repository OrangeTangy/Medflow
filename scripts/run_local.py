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
    try:
        return subprocess.call([str(python), '-m', 'uvicorn', 'app.local:create_local_app', '--factory', '--app-dir', str(project / 'backend'), '--host', '127.0.0.1', '--port', str(args.port)], cwd=project, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
