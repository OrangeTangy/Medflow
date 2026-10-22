# Run the main functions on one computer

Install Python 3.12 or newer, download/extract the source, and run from its folder:

```sh
python scripts/run_local.py
```

On Windows, `py scripts/run_local.py` also works. The first launch installs Python dependencies in `.venv`; later launches reuse them. No Docker, PostgreSQL server, Redis server, cloud service, or Node.js is required for the core functions.

Open **http://127.0.0.1:8000/local**. Create a local administrator and doctor account with separate emails/passwords. Sign in as the doctor and use **Record arrival**, **Record departure**, and **Save activity to database**. Administrators can select any doctor in this local organization; doctors can record/read only their own data.

Windows users can also double-click `start-local.bat`. On macOS/Linux, run `./start-local.sh`. Administrators can add more doctor accounts from the local page, with no frontend build required.

Each successful timestamp request is committed before the API confirms it. The immutable `local_timestamps` table preserves event time, server receipt time, doctor, facility, actor, and idempotency key. The `attendance_sessions` table stores arrival, departure, duration in seconds, and manual/unverified source. Duplicate retry IDs do not add time twice. Invalid ordering, overlapping sessions, and a second arrival before departure are rejected. UTC instants survive SQLite reloads and display in the facility’s configured IANA timezone.

The database lives at **`data/medflow.sqlite3`**. Closing the browser or restarting the server does not delete it. The database contains account hashes and operational records, so keep it in the private operating-system account that runs the program. SQLite single-computer mode does not provide PostgreSQL row-level security; keep the enterprise runtime for a multi-user hospital deployment.

The local page works immediately without a frontend build. To use the larger Next.js dashboard too:

```sh
npm ci
npm run build
python scripts/run_local.py
```

After sign-in, click **Full dashboard**. It uses the same real SQLite records as the simple timestamp page. The published Sites URL remains a separate fictional sandbox.

Back up the database (including writes captured in the WAL) with:

```sh
python scripts/run_local.py --backup backups/medflow-backup.sqlite3
```

Use `--port 8080` to choose another localhost port, or `--database /path/to/attendance.sqlite3` to choose a database. Back up before replacing a database; restore by stopping the app and starting with `--database` pointing to the restored copy.

## Sending timestamps from a program

Sign in at `POST /api/local/login` with `{"email":"doctor@local.test","password":"your password"}` and retain the HttpOnly session cookie. Send `Origin: http://127.0.0.1:8000` with every write. Get authorized facility IDs from `/api/locations` or `/api/dashboard`.

```http
POST /api/local/timestamps
Content-Type: application/json
Origin: http://127.0.0.1:8000
Cookie: medflow_session=<session-cookie>

{"event_type":"arrival","location_id":"<facility-id>","source_event_id":"computer-event-001"}
```

For departure, use `"event_type":"departure"` and a new event ID. Omit `event_timestamp` to capture server time, or provide an offset-bearing ISO timestamp such as `2026-10-22T08:02:00-04:00`. Reuse the **same** source event ID when retrying an uncertain request. Doctors cannot supply a different doctor ID. The response includes the saved database ID, UTC event and receipt timestamps, session ID, and duration seconds. Read saved events through `GET /api/local/timestamps`.

These are manual records. Automatic WiFi detection requires the enterprise RADIUS/controller integration; a browser cannot reliably infer WiFi attendance. Audio recording/playback remains available in the full dashboard; transcription and AI services are disabled in this standalone mode, and manual report entry works immediately.
