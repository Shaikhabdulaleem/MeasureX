# apps/mobile

Flutter (Dart) app for Labour and Team Leader.

**Milestone 0 (current):** skeleton with Riverpod state, localisation in
**English / Arabic (RTL) / Bengali**, a **login** screen, forced
**password-change** screen, and a **Home** screen with the big **SCAN SHIPMENT**
button (not wired yet) plus **sync** and **scale** status placeholders. Auth
talks to the API (`/auth/*`). Scanner, measurement, scale and sync land in M1+.

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
