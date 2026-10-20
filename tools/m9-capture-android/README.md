# M9 Capture (Android research instrument)

Isolated Kotlin + ARCore app that **captures metric pose data** for the MeasureX M9
real-device spike. It records real RGB frames, ARCore VIO camera poses (converted to
the M9 convention), per-frame CPU-image intrinsics, gravity and an optional support
plane — and **computes no dimensions**. All measurement happens offline (see
[`services/vision-poc/docs/M9_REAL_DEVICE_CAPTURE.md`](../../services/vision-poc/docs/M9_REAL_DEVICE_CAPTURE.md)).

Not wired into the production MeasureX Flutter app. No backend, auth, database, WMS,
Bluetooth, billing, ARCore Depth API or monocular depth.

## Build

Requires the Android SDK (compileSdk 36) and JDK 17+. From this directory:

```bash
./gradlew :app:testDebugUnitTest :app:assembleDebug
```

- Unit tests (JVM, no device): the mandatory coordinate-convention tests and the
  raw-manifest / capture-controller tests.
- Debug APK: `app/build/outputs/apk/debug/app-debug.apk`.

Install on a device:

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`local.properties` (SDK path) is machine-local and git-ignored; create it with
`sdk.dir=<your Android SDK path>` if your tooling does not.

## Device support

ARCore is not available on every phone (the current test device, Samsung Galaxy A16
4G, is not certified). The app checks availability at launch and, if unsupported,
blocks with *"Metric pose unavailable on this device. M9 metric capture cannot run."*
It never falls back to monocular depth.

## Capture procedure

See the physical procedure and coordinate/convention details in
[`M9_REAL_DEVICE_CAPTURE.md`](../../services/vision-poc/docs/M9_REAL_DEVICE_CAPTURE.md).
