# apps/mobile

Flutter (Dart) app for Labour and Team Leader. **Skeleton only** in Milestone 0
— no feature code yet.

Stack (PRD §14): Flutter + Riverpod, Drift + SQLCipher (encrypted local DB),
`mobile_scanner` (ML Kit barcode), `flutter_blue_plus` (BLE), a Kotlin plugin
for Bluetooth Classic, and the C++ measurement core via Dart FFI
([`../../packages/measure-core`](../../packages/measure-core)).

Billing figures are previewed with `@measurex/shared` formulas but the server
value is always final (see root `CLAUDE.md`). Scaffolding lands in M1.
