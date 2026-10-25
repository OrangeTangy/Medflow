# Android test build

[Download Medflow WiFi for Android 8+](https://github.com/OrangeTangy/Medflow/raw/refs/heads/main/downloads/medflow-wifi-android-test.apk)

This small, self-signed debug APK is included directly because release-asset upload authentication was unavailable in the build environment. It contains the native Java source under `android/`; it contains no pairing, credentials, or event database. Android requires approval to install from a browser/file manager. This is a testing build, not a production distribution.

Build validation: Android API 35, JDK 17, successful `assembleDebug` and `lintDebug` with no lint issues, and successful APK signature verification. Physical phone WiFi behavior still needs a real-device test. See [setup](../docs/WIFI-QUICKSTART.md). `SHA256SUMS.txt` contains the APK hash. Future source changes require rebuilding and updating this artifact; GitHub Actions also uploads its own test APK.
