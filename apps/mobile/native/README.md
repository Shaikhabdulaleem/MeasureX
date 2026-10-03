# Native platform snippets (MeasureX mobile)

The Flutter platform folders `apps/mobile/android/` and `apps/mobile/ios/` are
**git-ignored** (regenerated per developer with `flutter create .`). Any native
code we own therefore lives here, tracked, and is copied into the generated
project. Re-apply these after regenerating the platform folders.

## Android — Bluetooth scale (M2, PRD §9)

1. **Classic (SPP) plugin** — copy
   [`android/kotlin/com/example/measurex/ClassicScalePlugin.kt`](android/kotlin/com/example/measurex/ClassicScalePlugin.kt)
   to `android/app/src/main/kotlin/com/example/measurex/ClassicScalePlugin.kt`.

2. **Register it** — copy [`android/MainActivity.kt`](android/MainActivity.kt)
   over `android/app/src/main/kotlin/com/example/measurex/MainActivity.kt`
   (it instantiates `ClassicScalePlugin` in `configureFlutterEngine`).

3. **Permissions** — merge the entries from
   [`android/AndroidManifest.permissions.xml`](android/AndroidManifest.permissions.xml)
   into `android/app/src/main/AndroidManifest.xml`.

The Classic adapter is an Android-only **skeleton** behind the Dart
`ScaleAdapter` interface; it opens an RFCOMM/SPP socket to a paired scale and
streams raw bytes to Dart, which parses them with the shared `WeightParser`.
Device selection, reconnection and per-model framing are finished once a
concrete scale model is chosen (PRD §9, Q6).

## iOS

BLE (GATT) and HID-keyboard scales work on iOS via `flutter_blue_plus` and the
OS keyboard; Bluetooth Classic is **not** supported on iOS (needs MFi, PRD §9).
When the iOS project is regenerated, add `NSBluetoothAlwaysUsageDescription`
(and `NSBluetoothPeripheralUsageDescription`) to `ios/Runner/Info.plist` so BLE
scanning does not crash at runtime.
