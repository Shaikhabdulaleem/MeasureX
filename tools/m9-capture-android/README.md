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

- Unit tests (JVM, no device): the mandatory coordinate-convention tests, the
  raw-manifest / capture-controller tests, the JPEG write-gate and export-guard
  tests, the image/intrinsics dimension check and the ARCore availability decision.
- Debug APK: `app/build/outputs/apk/debug/app-debug.apk`.

Also built in CI — the `m9-android` job (JDK 17) runs the same
`:app:testDebugUnitTest :app:assembleDebug`. The APK is a CI artefact only and is
not uploaded.

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

While support is still being determined (ARCore reports `UNKNOWN_CHECKING`) the app
shows *"Checking ARCore support…"* and rechecks on the main looper; a hard
error/timeout blocks cleanly.

## Capture behaviour (on-device)

- **Each NEW SWEEP creates a brand-new ARCore `Session`** (old session paused,
  closed and replaced; new `session_id`), so the three sweeps initialise VIO —
  world origin and metric scale — independently. Poses are never averaged across
  sessions.
- **SET CARTON TARGET creates a real ARCore `Anchor`.** Its tracked pose is the
  guidance pivot (stability only — it imposes no dimensions) and is detached on a new
  sweep or on exit. The exported `guidance_target_world` is that anchor's pose,
  sampled on the render thread at the latest tracked frame before export, in the same
  world frame as the camera poses.
- **EXPORT waits for completed image writes.** Every accepted candidate's JPEG write
  is tracked; EXPORT is disabled while any write is pending or a referenced image
  failed, and the manifest/ZIP are written only after a final check that every
  referenced frame exists and is non-empty. A failed write drops that frame from the
  manifest and the controller so capture can replace it.
- **Completion target is 125°** (`count >= 12` **and** `coverage >= 125°`). The
  offline validator/selector still require only the 120° research minimum, giving
  selection margin without moving the research gate.
- **Orientation/image diagnostics** (`diagnostics.json`): `session_id`,
  `sweep_index`, `display_rotation`, CPU image and intrinsics width/height,
  `camera_id`, `sensor_orientation_deg` (when the platform exposes it, else null) and
  the camera config. The saved CPU image stays unrotated, unmirrored, uncropped and
  unresized; a candidate whose image grid does not equal its intrinsics grid is
  rejected and counted in `rejected_dim_mismatch`.

This is a data-capture instrument only: it has not yet been validated on a real
device.

## Capture procedure

See the physical procedure and coordinate/convention details in
[`M9_REAL_DEVICE_CAPTURE.md`](../../services/vision-poc/docs/M9_REAL_DEVICE_CAPTURE.md).
