# Your WiFi → device log → main computer notification

This runnable test uses **your exact WiFi network name**, an opted-in Android phone or desktop watcher, a paired receiver, and the main computer's local dashboard. It does not discover people merely by scanning an SSID. No WiFi password is collected. Hospital RADIUS/controller integration is a separate production capability.

## 1. Start the main computer

Install Python 3.12+, download/extract the [source](https://github.com/OrangeTangy/Medflow), and run from its folder:

```sh
python scripts/run_local.py --receive-devices --insecure-lan
```

Windows can use `py` instead of `python`. First launch installs dependencies. The console prints both services. This explicit **private LAN test** uses unencrypted HTTP for device events; do not forward its port to the Internet. Local accounts and the dashboard remain loopback-only at **http://127.0.0.1:8000/local**. Create separate administrator and doctor accounts, then sign in. The receiver listens separately on port **8765**, accepts only paired device events, and exposes no account/directory/report APIs.

For deployment, supply a certificate/private key instead:

```sh
python scripts/run_local.py --receive-devices --tls-cert /path/fullchain.pem --tls-key /path/privkey.pem
```

Use a hostname covered by a valid, phone-trusted certificate in the pairing URL, or terminate HTTPS with a properly configured reverse proxy/VPN. TLS verification is never disabled by the clients. The receiver's default rate limit is 240 events/minute per source address; account for shared reverse-proxy addresses when planning larger deployments.

## 2. Create a pairing for your WiFi

On the main computer, open **Pair a phone or computer**:

1. Enter a device name and your **exact SSID** (case and spaces matter).
2. Enter the receiver address the device can reach. For a LAN test this is, for example, `http://192.168.1.10:8765`, using the **main computer's LAN address**, not `localhost` or `127.0.0.1` on the phone.
3. Click **Create pairing**. Administrators first select a doctor; doctors can pair only themselves.
4. Copy the private JSON to the phone, or download `pairing.json` for the computer watcher. The token is displayed once, stored hashed on the receiver, and bound to one doctor/device/network. Keep it private; do not commit it to GitHub.
5. Click **Enable desktop alerts** and allow notifications. Keep the dashboard open. The event feed works even if browser/OS notification permission is denied.

Find the main computer's WiFi/LAN address in its network settings (macOS: WiFi Details → TCP/IP; Windows: `ipconfig`; Linux: `ip address`). Allow inbound TCP 8765 on the private-network firewall profile. Router guest/client isolation may prevent phones from reaching a computer on the same WiFi.

## 3A. Android phone (Android 8+)

Download [the Android test APK](https://github.com/OrangeTangy/Medflow/raw/refs/heads/main/downloads/medflow-wifi-android-test.apk), or build it as described below. Android may require you to allow installation from your browser/file manager. This is a self-signed test build, not a Play Store release or hospital deployment approval.

1. Install and open **Medflow WiFi**.
2. Paste the pairing JSON and tap **Save pairing**.
3. Tap **Allow WiFi permissions**, grant **precise location**, nearby WiFi permission when requested, and notification permission. Turn on Android **Location services**. Android treats WiFi names as location-sensitive data; the app does not record GPS coordinates.
4. Tap **Start monitoring** while the app is visible. A persistent notification remains; use its **Stop** action or the app's button to stop.
5. Starting connected records a clearly labeled initial observation. Turn WiFi **off** for about ten seconds, then turn it back **on** and reconnect.
6. Watch the phone's **Local event log (UTC)** and the main computer's **WiFi notifications** feed. Delivered events retain the original phone time plus the separate server receipt time.

The phone writes SQLite **before** attempting delivery. If mobile data or a routable VPN/HTTPS endpoint is available after disconnection, it can notify immediately. A private LAN receiver is normally unreachable when WiFi is off: the disconnect stays queued and both events arrive after reconnection. No app can send a packet while it has no path to the receiver.

Monitoring uses WiFi callbacks and three-second observations. It does not start automatically at boot. Force-stop, reboot, Doze, manufacturer battery restrictions, or revoked permissions can interrupt detection; reopen the app and start again. Observation gaps are marked unknown. SSID redaction/permission failures never become fabricated departures. A new process records a baseline rather than guessing a missing transition. Interruptions shorter than the observation/callback window can be missed. Device behavior must be tested on the actual phone.

## 3B. Windows, macOS, or Linux watcher

Put the downloaded private configuration on the device whose WiFi should be monitored, then run:

```sh
python scripts/watch_wifi.py --pairing /path/to/pairing.json
```

The pairing selects the SSID. Moving to another WiFi counts as leaving the selected network; redacted network names remain unknown. Linux requires NetworkManager/`nmcli`; macOS/Windows may require WiFi/location permissions. The watcher uses only the Python standard library. It commits events to local SQLite and JSONL, queues retries under that pairing identity, and reuses event IDs. Stop with Ctrl+C; stopping is not a departure. Keep using the same pairing/log directory to resume its outbox.

To test without a receiver:

```sh
python scripts/watch_wifi.py --ssid "Your WiFi name"
```

## Storage and access

- Main DB: `data/medflow.sqlite3`. Tables: `local_paired_devices`, `local_wifi_events`, `local_notifications`, plus the existing attendance/activity/account tables.
- Desktop outbox: `data/wifi-events.sqlite3`; readable copy: `data/wifi-events.jsonl`.
- Phone: private app SQLite; newest 30 log entries visible. Unsent observations are retained, and approximately the newest 1,000 delivered observations remain. App uninstall/clearing storage deletes this local queue and pairing.
- Backend accepts observations from the last 30 days. Older/clock-invalid or conflicting events (HTTP 422/409) are retained on the client for review and marked rejected, so they do not block delivery of later valid events. Token, rate-limit, and temporary network failures leave the outbox pending. Restore the correct phone clock and investigate rejected records; never fabricate replacement timestamps.
- Receiver event and notification creation are transactional. Retries deduplicate by event ID; conflicting IDs are rejected. Revocation and disabled doctor accounts reject further sends.
- Administrators see notifications for their organization; doctors see only their own. Pairing tokens grant write-only device reporting, never report/directory access. Notifications show operational device information, not transcripts.
- Main computer notifications require a running receiver and an open signed-in page. The feed catches up from its durable cursor after temporary outages. Browser/OS focus settings can suppress desktop popups.
- There is no automatic backend deletion of paired device logs in this local mode; use the documented backup/restore workflow and an approved retention policy before real workforce use.

These observations are labeled **device-reported/unverified**, kept separate from attendance sessions, and do not prove that a person was working. Multi-device trusted attendance reconciliation remains the enterprise RADIUS path. Consent/workforce policies, identity verification, actual network/phone validation, and HIPAA applicability/agreements still require administrative review before production use.

## Build the Android APK

Install JDK 17+ and the Android SDK (API 35/build-tools 35). Then:

```sh
cd android
./gradlew :app:assembleDebug :app:lintDebug
```

Windows uses `gradlew.bat`. The installable test APK is `android/app/build/outputs/apk/debug/app-debug.apk`. GitHub Actions builds and uploads the same test artifact. A distribution release needs an operator-owned signing key; never commit a key or pairing file. Debug builds from different machines/CI may have different signing keys and require uninstall/reinstall to upgrade, which deletes phone-local data. Deliver the queue first.

Run backend and queue/security tests with `.venv/bin/pytest -q` after installing `backend/requirements.txt`. Physical WiFi tests are intentionally separate from synthetic adapter/HTTP tests.

## Receiver API

The paired client sends `POST /api/events` with `Authorization: Bearer <pairing-token>` and `Content-Type: application/json`:

```json
{"id":"<stable-event-UUID>","event_type":"connected","observed_at":"2026-10-25T08:02:00Z","ssid":"Your WiFi name","initial_observation":false}
```

Use `disconnected` for leaving the selected network. `unknown`, `monitor_started`, and `monitor_stopped` preserve observer uncertainty without creating attendance. Reuse the original UUID and payload on retries. The authenticated pairing supplies the doctor and device; client identity overrides are rejected. A success response includes the original ID and `duplicate` status. Event time must include UTC/offset and fall within the last 30 days, with at most 60 seconds of future clock skew. The server commits before acknowledging.

The loopback account API provides `POST/GET /api/local/devices`, `POST /api/local/devices/{id}/revoke`, and `GET /api/local/notifications?after=<cursor>`. These require a signed-in local account and origin validation on writes. Pairing tokens cannot call them.
