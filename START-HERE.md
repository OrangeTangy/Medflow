# Start here: run Medflow on your own WiFi

This guide is for the person receiving the GitHub repository. Set up the main computer and phone at **your own site**, using your own accounts, WiFi name, and network address. A GitHub clone contains code; it contains no existing attendance database or usable pairing tokens. No ChatGPT/Sites account or access to the original developer's computer is needed.

The delivered application is a working WiFi/device logging and local attendance pilot. Read [FEATURE-STATUS.md](docs/FEATURE-STATUS.md) for the original requirements that still need implementation, configuration, or deployment validation.

## What you need

- A Windows, macOS, or Linux main computer with **Python 3.12+**, a browser, and Internet access for the first dependency installation. Linux may need its distribution's Python venv package.
- An **Android 8+** phone for phone monitoring, or a Windows/macOS/Linux computer running the watcher. A native iPhone app is not included.
- A trusted WiFi/LAN that permits devices to contact the main computer. No WiFi password is collected by Medflow.
- For the local pilot: no Docker, Node.js, PostgreSQL server, Redis server, IdP, or cloud account. These are separate requirements for the enterprise stack or optional larger dashboard.

## 1. Get a clean copy

Use **Code → Download ZIP** on [GitHub](https://github.com/OrangeTangy/Medflow) and extract it, or:

```sh
git clone https://github.com/OrangeTangy/Medflow.git
cd Medflow
```

Open a terminal in the extracted repository folder (the one containing this file). Check your Python version with `python --version`, `python3 --version`, or `py -3 --version` on Windows. Use the executable that reports Python 3.12 or newer. Record `git rev-parse HEAD` when using Git so another person can reproduce your exact source revision. Review the CI result for that revision; a passing build is separate from physical WiFi validation.

## 2. Start the main computer

For an explicit **private LAN test**:

```sh
python scripts/run_local.py --receive-devices --insecure-lan
```

On Windows, use `py -3` in place of `python`, or double-click **start-wifi-test.bat**. On macOS/Linux, use `python3`, or run `sh start-wifi-test.sh`. The helpers deliberately enable LAN-test HTTP; use the TLS command in the WiFi guide for deployment.

The first launch creates a project-specific `.venv` and installs the pinned local requirements. Wait until both services have started. Keep the terminal open.

| Service | Address | Who can use it |
| --- | --- | --- |
| Accounts and dashboard | http://127.0.0.1:8000/local | Browser on the main computer only |
| Device receiver | Main computer LAN address, TCP 8765 | Devices with a valid, revocable pairing token |

Open the dashboard and create **new** administrator and doctor accounts. Select the facility's IANA timezone (for example `Asia/Kolkata`, `Europe/London`, or `Africa/Nairobi`), rather than a fixed UTC offset. Event instants are stored in UTC. The pinned `tzdata` package supplies timezone data on systems, including Windows, that do not have an OS timezone database.

The basic local page works immediately. For the larger Next.js charts/recording interface, install Node.js 22, run `npm ci` and `npm run build`, then restart the local launcher and choose **Full dashboard**. Local automatic transcription and AI remain disabled.

## 3. Pair your phone with your WiFi

1. Sign in on the main computer. Administrators select the doctor; doctors can pair only their own device.
2. In **Pair a phone or computer**, enter a device name and the **exact WiFi SSID**, including case/spaces. This is a network name, not a password.
3. Find the main computer's LAN IP in network settings. Examples: Windows `ipconfig`; macOS WiFi Details → TCP/IP; Linux `ip address`.
4. Enter a receiver URL such as `http://192.168.1.10:8765`, replacing the example with the main computer's actual address. **Do not use the phone's localhost or copy someone else's IP.**
5. Create a pairing. Copy its private JSON into the Android app, or download `pairing.json` for a computer watcher. The token is shown once; each person/device should have its own pairing. Do not share it with the person receiving the source repository.
6. Click **Enable desktop alerts**, allow notifications, and keep the dashboard open.

Allow incoming TCP 8765 on the main computer's **private-network** firewall profile. Guest WiFi/client isolation may prevent this connection even when both devices use the same SSID. Port 8000 stays loopback-only.

## 4. Install the Android app and test

[Download the Android test APK](https://github.com/OrangeTangy/Medflow/raw/refs/heads/main/downloads/medflow-wifi-android-test.apk). Its SHA-256 is published in [downloads/SHA256SUMS.txt](downloads/SHA256SUMS.txt). This is a self-signed test build, not a Play Store/production release; Android may ask to allow installation from the browser/file manager.

Open **Medflow WiFi**, paste your pairing JSON, and tap **Save pairing**. Allow precise location, nearby WiFi and notifications when requested; turn on Android Location services so the OS can reveal the WiFi name. Medflow does not record GPS coordinates. Tap **Start monitoring** while the app is visible. A persistent notification lets you stop monitoring.

Turn WiFi off for about ten seconds, then on and reconnect. Verify a disconnect followed by a reconnect in the phone's **Local event log (UTC)** and the main computer's **WiFi notifications** feed. Initial observations are labeled as baselines. Phone time and server receipt time remain separate.

**Offline delivery:** if turning WiFi off removes the route to the receiver, events stay on the phone and arrive after reconnection. Mobile data cannot reach a private LAN address without appropriate routing/VPN. Monitoring interruptions, permissions, device sleep, force-stop and reboot require real-device testing; restart monitoring after reboot. The dashboard must remain open for browser desktop alerts. Email/SMS/closed-browser push is not included.

For a computer instead of a phone, put its private pairing file on that computer and run:

```sh
python scripts/watch_wifi.py --pairing /path/to/pairing.json
```

The standard-library watcher uses native Windows/macOS WiFi APIs or Linux NetworkManager/`nmcli`. It does not run on an iPhone. See [WiFi details](docs/WIFI-QUICKSTART.md).

## 5. Verify the handoff

After the first install, stop the launcher with Ctrl+C and run:

```sh
python scripts/verify_local.py
```

It selects this repository's virtual environment and runs a synthetic user journey against a **temporary SQLite database**: setup, role access, UTC duration, saved activity, paired events, notification deduplication/revocation, restart persistence, and backup. It does not read the real attendance database, contact the hospital network, prove WiFi hardware compatibility, or establish compliance. GitHub Actions runs it from clean Windows/macOS/Linux checkouts using only the local requirements.

Then perform the real acceptance check at your site:

- Sign in as a doctor, save an arrival/departure and activity, and confirm the calculated duration.
- Pair your own device; switch WiFi off/on and confirm the original observation timestamps and eventual notifications. An initial baseline is not an inferred earlier arrival.
- Restart the server and confirm your saved records remain.
- Sign in as a different doctor and confirm the first doctor's records/notifications are inaccessible; confirm the administrator can review the organization.
- Revoke a pairing and confirm that it can no longer send events.

WiFi phone events **do not automatically create attendance sessions or work-hour totals**. Manual attendance is stored separately, while enterprise network reconciliation requires trusted RADIUS/controller integration.

## 6. Keep your data and recover it

Main data is in `data/medflow.sqlite3`. Keep it private; never send the database, `.env`, credentials, or pairing files with a source-code handoff. SQLite access is controlled by the OS account, not PostgreSQL RLS. People using doctor web accounts must not be given direct database/file access.

Create a backup while the app runs or after stopping it:

```sh
python scripts/run_local.py --backup backups/site-backup.sqlite3
```

Restore by stopping the app and launching with `--database /path/to/restored-copy.sqlite3`. Do not replace the live file while it is open. Upgrading/removing the Android test app can delete its queue; deliver queued events first. Debug APKs built on different machines can use different signing keys.

## If it does not work

| Symptom | Check |
| --- | --- |
| Python/venv missing | Install Python 3.12+; enable Python on PATH or use Windows `py -3`. On Linux install the matching venv package. |
| Dependency install fails | First installation needs access to Python's package index. Keep TLS verification enabled; configure your organization's approved proxy/CA if required. |
| Port already in use | Stop the other instance, or use `--port 8080 --receiver-port 8766`; update the phone's receiver URL to match. |
| Phone cannot reach receiver | Use the main computer's actual LAN IP, TCP 8765, private firewall profile, and a network without client isolation. |
| WiFi state unknown | Allow precise location/WiFi permission, enable Location services, and check phone background/battery restrictions. Unknown evidence is not a departure. |
| No immediate disconnect popup | If no route remains, reconnect first. Keep the main dashboard open and allow browser/OS notifications. |
| Receiver returns 401 | Pairing was revoked, token is wrong, or doctor account is disabled; create a fresh pairing as appropriate. |
| Observation rejected | Check device clock, selected SSID and event age. Invalid/conflicting events are retained for review; do not invent replacement timestamps. |
| Timezone rejected on Windows | Rerun the launcher to install updated requirements, then run `python scripts/verify_local.py`. |

## Overseas use and hospital deployment

Someone overseas can replicate this at their own site using their own WiFi and local main computer. Geography does not require access to the original developer's accounts. If the main computer and reporting device are in **different countries/networks**, a matching SSID does not connect them: deploy an approved, reachable HTTPS receiver/VPN and review local data residency/monitoring policies. Never expose the LAN HTTP test port directly to the Internet.

For the hospital deployment foundation, use [DEPLOYMENT.md](docs/DEPLOYMENT.md) and [ACCEPTANCE.md](docs/ACCEPTANCE.md). This requires hospital-specific identity, equipment, providers, security/privacy review, load tests, and recovery validation. It is a different setup from the simple local pilot.
