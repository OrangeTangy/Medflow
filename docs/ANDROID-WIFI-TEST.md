# Test WiFi connect/disconnect on your Android phone now

**Medflow now includes its own Android app and paired live notifications.** For that complete flow, follow [WiFi quick start](WIFI-QUICKSTART.md) and download [the test APK](https://github.com/OrangeTangy/Medflow/raw/refs/heads/main/downloads/medflow-wifi-android-test.apk). The MacroDroid steps below remain an optional phone-only logging/import alternative when no main computer is running.

The test must run on the phone. The web dashboard and the cloud build workspace cannot observe your phone’s WiFi association. You do not need a Mac, Python, or a server for this first test.

## 1. Install the automation app

Install [MacroDroid from Google Play](https://play.google.com/store/apps/details?id=com.arlosoft.macrodroid). This is a third-party automation app, separate from Medflow. Two automations are enough. Choose **Any Network** for this first test; it avoids having to identify a particular SSID. The WiFi trigger supports both network connections and disconnections.

## 2. Create the connected macro

In MacroDroid, tap **Add Macro**:

- **Trigger → Connectivity → WiFi State Change → Connected to Network → Any Network**.
- **Action → Logging → Log Event**. The action name is **Log Event**; its category may vary by app version.
- Set its message to `MEDFLOW|connected|{system_time_ms}`.
- Use the message field’s **Magic Text** selector to insert **System time (ms)** for the last value, rather than typing a fixed number.
- Name the macro **Medflow WiFi connected** and save it with no constraints.

## 3. Create the disconnected macro

Add a second macro:

- **Trigger → Connectivity → WiFi State Change → Disconnected from Network → Any Network**.
- **Action → Log Event** with the message `MEDFLOW|disconnected|{system_time_ms}`.
- Insert **System time (ms)** with Magic Text again.
- Name it **Medflow WiFi disconnected**, save it with no constraints, and enable both macros.

If Android prompts for WiFi-related permissions, follow the app’s prompt. If no events appear while the app is in the background, allow MacroDroid to run with unrestricted battery usage. Some phone/Android versions require location permission/services for WiFi details. No SSID is needed in these log messages.

## 4. Perform a real test

1. Keep MacroDroid enabled and start connected to WiFi.
2. Open Android Quick Settings and turn WiFi **off**. Wait 5–10 seconds.
3. Turn WiFi **on** and wait until it reconnects. Wait another 5–10 seconds.
4. Open MacroDroid’s **User Log** (not just the System Log).

Look for a disconnected entry followed by a connected entry, each with a timestamp. For example, a message may look like `MEDFLOW|disconnected|1792710000123`; the number comes from your phone’s clock. The entries are saved by the phone app, so an Internet connection is not needed to write the disconnect event. Force-stopping MacroDroid prevents its automations from running; repeat the test after reopening it if necessary.

This has not been tested on your physical phone. The app’s own timestamped User Log is the first thing to verify before connecting a backend.

## 5. Import into Medflow when a local server is available

Copy or export the User Log as text. On the computer running `python scripts/run_local.py`, open `/local`, sign in as your doctor account, and use **WiFi device test → Import Android log**. You can select a text file or paste the copied entries.

The importer reads only the `MEDFLOW|...` markers. It converts epoch milliseconds to UTC, checks times against the last 30 days, assigns the logged-in doctor server-side, deduplicates repeated imports for the same device ID, and saves the events in `local_wifi_events`. Unrelated log text is ignored and not stored. Reuse the same device ID when importing another file from the same phone. Do not import another person’s log into your account.

The phone can log offline now. This local import happens later and does not require opening a laptop’s localhost server to the Internet. The private Sites sandbox is a separate runtime; this local import does not upload to that site.

These are **phone-reported test observations**, not RADIUS evidence or proof of a person’s presence/work. Importing does not alter attendance sessions or label a shared home network as an authenticated hospital network.

## Reference documentation

- [MacroDroid WiFi State Change trigger](https://macrodroidforum.com/wiki/index.php/Trigger%3A_Wifi_State_Change)
- [MacroDroid Log Event action](https://macrodroidforum.com/wiki/index.php/Action%3A_Log_Event)
- [MacroDroid User Log](https://macrodroidforum.com/wiki/index.php/User_Log)
- [Magic Text, including epoch milliseconds](https://macrodroidforum.com/wiki/index.php/Magic_text)
