# apps/mobile

Flutter (Dart) app for Labour and Team Leader.

**Milestone 1 (current):** scan & capture. On top of the M0 auth skeleton:
AWB **scanner** (`mobile_scanner`, Code128 + QR, regex-filtered, beep + vibrate,
torch, manual entry), **history check** (new / open / completed with "Flag for
Team Leader" for Labour and "Remeasure" for TL/Admin), **manual dimensions**
(L/W/H cm, 1–300, mandatory photo), **review** with a billing preview from the
shared Dart formulas ([`lib/src/core/billing.dart`](lib/src/core/billing.dart)),
**save → add another / complete → summary → scan next**, and a **history** list
with shipment detail. All strings in **English / Arabic (RTL) / Bengali**. Scale
and offline sync land in M2–M3.

Full stack target (PRD §14): Flutter + Riverpod, Drift + SQLCipher, ML Kit
scanning, `flutter_blue_plus`, a Kotlin Bluetooth-Classic plugin, and the C++
measurement core via FFI ([`../../packages/measure-core`](../../packages/measure-core)).

## First-time setup

This repo holds the Dart source (`lib/`, `test/`, `pubspec.yaml`, ARB files)
but not the generated platform folders. Scaffold them once — `flutter create`
adds `android/`, `ios/`, etc. and will not overwrite the existing `lib/`:

```bash
cd apps/mobile
flutter create .
flutter pub get          # also generates localisations
```

**Local dev talks to the API over plain HTTP, which Android blocks by default.**
For development, allow cleartext to your dev host by adding to
`android/app/src/main/AndroidManifest.xml` on the `<application>` tag:

```xml
<application
    android:usesCleartextTraffic="true"
    ... >
```

(Production uses HTTPS, so this is a dev-only convenience.)

**Camera permission (M1).** The scanner and the mandatory photo need the camera.
Add to `android/app/src/main/AndroidManifest.xml` above `<application>`:

```xml
<uses-permission android:name="android.permission.CAMERA" />
```

`mobile_scanner` needs Android `minSdkVersion` 21+ (Flutter's default). For iOS,
add `NSCameraUsageDescription` to `ios/Runner/Info.plist`.

## Run

With the API running and reachable (see root `README.md`):

```bash
flutter run              # Android emulator reaches the host API at 10.0.2.2
```

Point the app at a specific API (e.g. your PC's LAN IP from a physical phone on
the same Wi-Fi):

```bash
flutter run --dart-define=API_URL=http://192.168.1.50:3000/api/v1
```

Checks: `flutter analyze` and `flutter test`.
