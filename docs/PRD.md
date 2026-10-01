# MeasureX — Final PRD v2.0

Oct 1, 2026 · @shayan

## 1. Summary

MeasureX is an internal Aymakan app that lets warehouse workers dimension and weigh shipments with their own phone, a printed marker mat and a Bluetooth scale, then saves every result with a photo and a full audit trail. Version 2.0 replaces v1.0 as the build reference for Claude Code.

**Core worker flow:** Scan AWB → Place on mat/scale → Point phone → Confirm → Next.

**What changed from v1.0**

- **Measurement method:** a marker-mat station replaces "point anywhere" camera measurement, so it works on ordinary phones without depth sensors. Markerless AR becomes a later upgrade.
- **Manual entry fallback:** Labour can enter dimensions manually when automatic measurement fails; every manual entry is flagged and reported.
- **No Aymakan integration in this release:** the worker scans only the tracking number (AWB) and goes straight to measurement; nothing else is entered. A pluggable backend adapter lets Aymakan be connected later.
- **Phased delivery:** Phase A ships a full working platform with manual and scale capture; Phase B adds marker-mat measurement; Phase C adds AR.
- **New rules defined:** AWB format, chargeable weight, rounding, state machines, sync conflict rules, BYOD device rules, data residency.
- **Contradictions in v1.0 resolved** (remeasure permissions, Low-confidence blocking, client source, Team Leader platforms).

**Scope owner:** Aymakan operations. **Users:** Labour, Team Leader, Admin/Operations Manager. **Platforms:** Android, iOS, web dashboard.

## 2. Decisions and assumptions

Confirmed decisions are fixed for the build; assumptions (marked A) are defaults Claude Code will implement as configurable until you confirm them.

**Confirmed**

| # | Decision |
| --- | --- |
| D1 | Internal Aymakan tool. No multi-tenant layer. "Client" = Aymakan's shipper customers (e.g. Arabian Oud). |
| D2 | Works on workers' own phones (BYOD), Android and iOS. |
| D3 | Measurement engine is built fully in-house. |
| D4 | Measurement uses a printed marker mat at a fixed station. |
| D5 | Labour may use manual dimension entry as a flagged fallback. |
| D6 | Bluetooth scales: BLE and Bluetooth Classic both supported. |
| D7 | Team Leader uses both the mobile app and the web dashboard. |
| D8 | No in-house dev team: Claude Code builds; stack is kept small and well documented. |

**Assumptions to confirm**

| # | Assumption (default) |
| --- | --- |
| A1 | AWB format is `AY` + 11 digits (from sample label `AY20435032852`). |
| A2 | Confirmed: no Aymakan integration for now. The worker scans only the tracking number and goes straight to measurement: no client, piece count or declared weight is entered. |
| A3 | Every piece of a multi-piece shipment carries the same AWB label; the app counts pieces against "Pieces". |
| A4 | Default volumetric divisor 5000 (cm, kg); one global value until shipments carry a client. |
| A5 | Each billing dimension is rounded **up** to the next whole cm; chargeable weight rounded up to the next 0.5 kg (configurable). |
| A6 | Actual weight is mandatory by default (configurable). |
| A7 | Medium confidence can be confirmed by Labour and is flagged; Low is always blocked. |
| A8 | Photos kept 12 months; synced local data purged from the phone after 7 days; unsynced data never auto-deleted. |
| A9 | Hosting in a Saudi cloud region (PDPL). Provider chosen in Milestone 0. |
| A10 | Most daily volume is small and medium cartons; pallets and bulky items are a minority. |

## 3. Users, roles and permissions

Three roles; each user belongs to one home branch, and Admins can be scoped to one branch or all branches.

| Function | Labour (mobile) | Team Leader (mobile + web) | Admin (web, mobile optional) |
| --- | --- | --- | --- |
| Scan AWB, measure, weigh, confirm | Yes | Yes | Yes |
| Manual dimension entry (flagged) | Yes | Yes | Yes |
| Confirm Medium confidence | Yes (flagged, per A7) | Yes | Yes |
| Confirm Low confidence | No | No (must retake or enter manually) | No |
| Perform a requested remeasurement | Yes | Yes | Yes |
| Request remeasurement | No; can "Flag for Team Leader" | Yes | Yes |
| Correct a measurement (reason required) | No | Yes | Yes |
| Reopen a completed shipment | No | Yes | Yes |
| History | Own measurements, last 7 days | Own branch | Scoped branches |
| Audit log | No | Own branch (read) | Yes |
| Users, branches, clients, configuration | No | No | Yes |
| Reports and export | No | Own branch | Yes |

**Account rules**

- Login with Employee ID + password; first login forces a password change.
- 5 failed attempts lock the account for 15 minutes; Admin can unlock and reset passwords.
- Session: 12-hour shift token with refresh; works offline until expiry (see section 10).
- Shared phones are allowed: logout requires all records synced, or shows a warning that pending records stay on the device under the previous user.

## 4. Measurement approach

Measurement happens at a fixed station: a printed ArUco marker mat, ideally lying on the scale platform, so one placement gives dimensions and weight on any phone with a camera.

**Measuring station**

- Mat: matte vinyl, about 100 × 100 cm, 8 ArUco markers (10 × 10 cm, dictionary `DICT_4X4_50`) around a marked placement zone. Each mat has a printed station ID.
- Pallet station: larger markers (20 × 20 cm) taped or painted on the floor around a marked pallet spot (Phase C).
- Mat file and marker layout are generated by the project (a script in the repo), so mats can be reprinted.

**Measurement method (Phase B, cartons and boxes)**

1. Detect at least 2 markers → compute camera pose, floor plane and real-world scale.
2. Segment the box inside the placement zone (edge and contour detection on the image).
3. Fit the box's base rectangle on the floor plane → length and width.
4. Find the top face edges → height from the camera pose.
5. Repeat over 5–10 consecutive frames; result = median; spread between frames feeds confidence.

Orientation rule: **Length = longest horizontal side, Width = shorter horizontal side, Height = vertical.** The engine stores millimetres; billing values are rounded per A5.

**Confidence rules (initial, tuned in calibration)**

| Level | Rule (all must hold) | Worker action |
| --- | --- | --- |
| High | ≥ 4 markers visible, frame-to-frame spread ≤ 1 cm, box fully inside zone, no occlusion | Confirm |
| Medium | ≥ 2 markers, spread ≤ 2.5 cm | Retake recommended; confirm allowed (A7, flagged) |
| Low | Anything else | Retake or manual entry; cannot confirm |

**Device tiers (BYOD)**

| Tier | Requirement | Allowed |
| --- | --- | --- |
| Standard | Android 9+ or iOS 15+, rear camera with autofocus, ≥ 3 GB RAM | Marker-mat measurement + manual |
| AR (Phase C) | ARCore-supported Android, or iPhone with ARKit; LiDAR preferred | Adds markerless and pallet measurement |
| Unsupported | Below Standard | Manual entry only; flagged on the dashboard |

The app checks the tier on first login and records it on the Device record.

**Manual entry fallback**

- Available to every role when the result is Low, the device is Unsupported, or the item does not fit the mat.
- The worker types L, W, H (cm) and must take a photo, ideally with the tape visible.
- Stored with `method = manual`; shown as a KPI: manual-entry rate per worker and branch. A configurable threshold alerts the Team Leader.

**Engine architecture:** one C++ core using OpenCV, shared by Android and iOS and called from Flutter through FFI. This keeps a single vision codebase for a team without native specialists. Phase C AR runs in thin native modules (ARCore / ARKit) behind the same `MeasurementEngine` interface.

## 5. Worker workflow

The worker scans the tracking number and goes straight to measuring; a single carton needs only scan, confirm and complete.

&#91;embedded content: worker flow · 7 steps, 3 decisions\]

Low confidence loops back to placing the box; a remaining piece loops back to the mat; the last piece completes the shipment automatically.

**Happy path**

1. **Home** → tap **SCAN SHIPMENT**.
2. **Scan AWB** → app accepts only codes matching the AWB format, vibrates + beeps, continues automatically.
3. **History check** → no input from the worker; the app checks whether this AWB already has packages in MeasureX (online) and goes straight on.
4. **Existing measurements?**
   1. None → continue to step 5 as PKG 01.
   2. Shipment still open → next package number continues (e.g. PKG 03).
   3. Shipment already completed → show previous result; options: View, Flag for Team Leader (Labour) or Remeasure (Team Leader/Admin, or anyone if a remeasurement is requested).
5. **Place** → instruction: "Place the box on the mat" (and on the scale).
6. **Measure** → camera view with live guidance; dimensions appear when confidence is reached; photo captured automatically.
7. **Weigh** → stable weight captured automatically from the scale, in parallel with step 6.
8. **Review** → photo, L × W × H, CBM, volumetric, actual and chargeable weight, confidence, and divisor used.
9. **Confirm & Save** → saved locally first, then synced.
10. **Next piece or done** → the worker taps Add Another Package (back to step 5) or Complete Shipment. An open shipment auto-completes after 30 minutes idle (configurable).
11. **Summary** → totals; **Scan Next AWB** is the primary button.

**Exception paths**

- Scan fails → Enter AWB manually (validated against the AWB format).
- Package saved under the wrong AWB → Team Leader voids it (reason required) and it is measured again.
- Low confidence → Retake (primary) or Enter manually.
- Item doesn't fit the mat → Enter manually.
- Scale missing or unstable > 10 s → retry, or continue without weight only if A6 allows it.
- Same AWB measured on two phones offline → both kept, flagged possible duplicate for the Team Leader.
- Offline → banner; flow continues; duplicate check marked "cannot verify".

**Mobile screens (Labour)**

Login · Home · AWB scanner · Manual AWB entry · Previous measurements · Measure (camera) · Manual dimensions · Review · Package saved · Shipment summary · History · Shipment detail · Sync queue · Settings (account, language, units, scale, device check, sync, logout).

**Additional mobile screens (Team Leader)**

Remeasurement queue · Flags from workers · Correct measurement (original vs new + reason) · Reopen shipment · Team history.

## 6. AWB label, scanning and shipment details

The worker scans only the tracking number (AWB) and goes straight to measurement; nothing else on the label is entered or pulled from Aymakan in this release.

**Aymakan label (sample AY20435032852)**

| Label field | Example | Used by MeasureX |
| --- | --- | --- |
| AWB barcode (Code128, printed twice) | AY20435032852 | Primary key; scanned |
| Account number (top left) | 3001111028 | To confirm: possibly client account (open question Q2) |
| QR code | AYM0000831 | Ignored until its content is known (Q2) |
| Origin / Destination | RUH / ON | Not used in this release |
| Pieces | 1 | Not used; worker adds packages one by one |
| Weight | 0.517 | Not used in this release |
| From | Arabian Oud | Not used in this release |
| Ref. | 290344194 | Not used in this release |
| Consignee name, phone, address | — | **Not stored.** Personal data; see photo rule below |

**Scanning rules**

- On-device scanning (Google ML Kit through the Flutter `mobile_scanner` package); works offline.
- Symbologies enabled: Code128 and QR (QR read but ignored unless Q2 says otherwise).
- Accept only values matching the AWB pattern `^AY\d{11}$` (A1, configurable regex). Other barcodes on the box are ignored silently.
- Torch toggle; manual entry with the same validation; normalise to upper case, strip spaces.

**What is captured**

- Only the AWB is captured: no client, piece count, declared weight or reference.
- A repeat scan of a known AWB shows its existing packages from MeasureX.
- Shipment data sits behind a backend `ShipmentSourceAdapter` (AWB only today), so Aymakan can be connected later without changing the app.
- When integration arrives: client, expected pieces, declared weight, client-specific divisors and weight-discrepancy flags are switched on.

**Photo privacy rule:** shipment photos show the label, which holds consignee personal data. Photos are stored privately (signed URLs only), kept per A8, and viewable only by Team Leader and Admin roles. Optional later: auto-blur the address block.

## 7. Business rules and calculations

All values are stored in integer base units (millimetres, grams) and every billing figure is computed on the server from those, so mobile and web always agree.

**Units**

- Stored: dimensions in mm (integer), weight in g (integer).
- Display: cm (default), mm, m or inches per user setting; billing always in cm and kg.

**Formulas** (billing dimensions L, W, H in whole cm after rounding up)

```latex
L_{cm} = \lceil L_{mm} / 10 \rceil
```

```latex
\text{CBM} = \frac{L \times W \times H}{1\,000\,000}
```

```latex
\text{Volumetric kg} = \frac{L \times W \times H}{\text{divisor}}
```

```latex
\text{Chargeable kg} = \text{round up to step}\left(\max(\text{actual}, \text{volumetric})\right)
```

- Divisor: one global value (A4). The divisor used is saved on each package.
- Rounding step for chargeable weight: 0.5 kg default (A5), configurable.
- CBM shown to 4 decimals; weights to 0.1 kg (actual) and 0.5 kg step (chargeable).
- Irregular items: the UI says "Bounding dimensions".

**Worked example:** 45.2 × 30.1 × 20.4 cm → 46 × 31 × 21 cm → CBM 0.0299, volumetric 5.99 kg (÷ 5000), actual 4.8 kg → chargeable 6.0 kg.

**Multi-piece rules**

- Next package number = highest confirmed number + 1 (server is final; see section 10 for offline).
- The worker adds packages one by one and taps Complete Shipment; an idle open shipment auto-completes after 30 minutes.
- Without integration there is no expected total, so over-delivery checks wait for it.
- Shipment totals (count, CBM, actual, volumetric, chargeable) = sum of active packages; recomputed on every change.

**Validation and flags**

- Each dimension 1–300 cm for the mat station (configurable); outside the range → manual entry required.
- Later, with integration: actual vs declared weight > 20 % → flag `weight_discrepancy`.
- Volumetric vs actual > 3× → flag `check_dimensions`.
- Flags never block saving; they appear in the dashboard and the Team Leader queue.

## 8. State machines

Every status change is a server-validated transition and writes an audit entry; any transition not listed here is rejected.

**Shipment**

| From | Event | To | Who |
| --- | --- | --- | --- |
| (new) | First package confirmed | `in_progress` | Any role |
| `in_progress` | Confirmed pieces = expected, or Complete tapped | `completed` | Any role / system |
| `completed` | Reopen (reason required) | `in_progress` | Team Leader, Admin |
| `completed` | Remeasurement requested | `remeasure_required` | Team Leader, Admin |
| `remeasure_required` | All requested packages remeasured | `completed` | System |
| `remeasure_required` | Request cancelled | `completed` | Team Leader, Admin |

**Package**

| From | Event | To | Notes |
| --- | --- | --- | --- |
| (new) | Confirm & Save | `active` | Version 1 created |
| `active` | Correction saved | `active` | New version; old version kept |
| `active` | Remeasured | `superseded` | Replaced by a new package row with the same number |
| `active` | Voided (wrong AWB, reason required) | `void` | Team Leader, Admin; excluded from totals |

**Remeasurement request**

| From | Event | To |
| --- | --- | --- |
| (new) | Requested with reason | `open` |
| `open` | Worker scans the AWB and confirms a new measurement | `done` |
| `open` | Cancelled | `cancelled` |

Reasons: low confidence, incorrect dimensions, bad photo, device issue, customer dispute, manual verification, other (text required).

**Sync record (mobile, per package)**

| From | Event | To |
| --- | --- | --- |
| (new) | Saved on phone | `pending` |
| `pending` | Upload starts | `syncing` |
| `syncing` | Server accepts | `synced` |
| `syncing` | Network or server error | `failed` (auto-retry with backoff, plus manual Retry) |
| `syncing` | Server flags a conflict | `conflict` (kept on server, routed to Team Leader) |

## 9. Bluetooth scale integration

Scales plug in through adapters behind one interface; three connection types are supported, but Bluetooth Classic works on Android only.

| Connection | Android | iOS | Notes |
| --- | --- | --- | --- |
| BLE (GATT) | Yes | Yes | Preferred for new scales |
| Bluetooth Classic (serial / SPP) | Yes | No (needs MFi certification) | Many existing industrial scales |
| HID keyboard mode | Yes | Yes | Scale "types" the weight; universal fallback |

**Adapter interface** (`ScaleAdapter`): `connect()`, `disconnect()`, `stream()` → raw readings, `parse(bytes)` → grams + stable flag, `tare()` if supported, `status()`.

**Stable weight rule (default):** 5 consecutive readings within ±20 g over at least 1.5 s, value > 50 g. Values configurable per scale model.

**Behaviour**

- Pair once per station; the app remembers the station's scale and reconnects automatically.
- Weight captured automatically when stable; the review shows the source (scale model + "stable").
- Never save a value from an unstable, stale (> 5 s old) or disconnected reading.
- Manual weight entry: Team Leader only, reason required, flagged `manual_weight`.
- Scale states shown: connected, connecting, disconnected, reading, unstable, stable, error.

**Certification:** a scale model is "approved" only after its adapter passes a test with known weights (1, 10, 50 kg). Admin keeps the approved-model list. **First model to be chosen in Milestone 2** (open question Q6).

## 10. Offline and sync

The phone is the first place every record is saved; the server is the final authority on package numbers and conflicts.

**Works offline:** scanning, known shipments on this device, measurement, photos, scale, manual entry, history of this device, sync queue.

**Needs connection:** first login on a device, previous-measurement check across devices, Team Leader corrections and reopen.

**Rules**

1. Every package gets a client-generated UUID and an idempotency key; resending the same record never creates a duplicate.
2. Offline package numbers are **provisional** (shown as "PKG 02\*"). On sync the server assigns final numbers in order of `confirmed_at`.
3. Two devices measuring the same AWB offline: both packages are kept. If the total exceeds expected pieces, the shipment gets `possible_duplicate` and goes to the Team Leader queue, with both photos side by side.
4. Upload order: package data first, then photos (resumable, compressed to max 1600 px, JPEG quality 80, \~300 KB). A package is `synced` only when its photo is stored.
5. Auto-sync on reconnect and every 60 s while pending; exponential backoff on failure; manual Retry always available.
6. Offline login: allowed for the last user of the device until the token expires (12 h shift + 12 h grace). After that, online login is required.
7. Local database encrypted (SQLCipher); photos in app-private storage; everything wiped on logout once synced.
8. Offline duration limit: none for capture; warning banner after 4 hours of unsynced records; storage warning at 500 MB.

**Offline banner:** "OFFLINE MODE — measurements are saved on this phone and will sync automatically." Duplicate-check screen shows: "Previous measurements can't be checked while offline."

## 11. Team Leader tools and web dashboard

The web dashboard is desktop-first, in English and Arabic (RTL), and every list filters by branch, date range, employee, confidence, method, flag and sync status.

| Page | What it shows | Key actions |
| --- | --- | --- |
| Dashboard | KPIs for today and the chosen range; flags waiting; pending sync by branch | Drill into any KPI |
| Shipments | AWB, branch, pieces, CBM, actual, volumetric, chargeable, confidence, method, flags, measured by/at, sync | Search, filter, export |
| Shipment detail | Totals + each package: photo, L×W×H, weights, confidence, method, device, scale, versions | View photo, Correct, Request remeasure, Void, Reopen, Audit |
| Review queue | Flags: low/medium confidence, manual entry, weight discrepancy, piece mismatch, possible duplicate, worker flags | Approve, Correct, Remeasure, Dismiss with note |
| Remeasurements | Open requests, age, reason, requester | Cancel, view result |
| Sync issues | Failed and conflict records by device and user | Resolve, contact worker |
| Clients | Later: used once shipments carry a client | Create, edit, deactivate |
| Branches | Name, code, stations, users, today's volume, pending sync | Create, edit |
| Stations | Station ID, branch, mat size, linked scale | Create, print mat |
| Users | Employee ID, name, role, branch, status, last active, measurements today | Create, edit, reset password, unlock |
| Devices | Model, OS, tier, last user, last sync | Block device |
| Reports | Daily volume, productivity per worker, accuracy/calibration, flags, manual-entry rate | Export Excel / CSV |
| Audit log | Time, user, role, entity, action, before, after, reason | Filter, export |
| Configuration | Units, languages, AWB regex, divisor, rounding, confidence thresholds, Medium allowed, weight required, flag thresholds, retention, scales | Edit (audited) |

**Correction screen:** original values next to new values; reason is mandatory; saving creates a new version, recalculates totals and writes an audit entry. Corrections from mobile (Team Leader) use the same API.

## 12. Data model

PostgreSQL, UUID primary keys, `created_at`/`updated_at` on every table, soft delete only; integers for mm and g.

| Table | Key fields |
| --- | --- |
| `branch` | id, code, name, status |
| `client` | id, code, name, aymakan\_account\_no, volumetric\_divisor (nullable), status |
| `user` | id, employee\_id, name, role (labour / team\_leader / admin), home\_branch\_id, admin\_scope (branch ids or all), password\_hash, must\_change\_password, failed\_logins, locked\_until, status |
| `station` | id, code, branch\_id, mat\_size\_mm, marker\_size\_mm, scale\_id |
| `scale` | id, model, connection (ble / classic / hid), adapter\_key, approved |
| `device` | id, install\_id, manufacturer, model, os, os\_version, tier (standard / ar / unsupported), last\_user\_id, last\_seen\_at, blocked |
| `shipment` | id, awb (unique), branch\_id, client\_id, expected\_pieces, declared\_weight\_g, origin, destination, client\_ref (all nullable, for a future integration), status, flags\[\], totals (pieces, cbm, actual\_g, volumetric\_g, chargeable\_g), completed\_at |
| `package` | id (client UUID), shipment\_id, package\_number, provisional\_number, status (active / superseded / void), current\_version\_id, station\_id, device\_id, measured\_by, confirmed\_at, sync\_received\_at |
| `measurement_version` | id, package\_id, version\_no, length\_mm, width\_mm, height\_mm, actual\_weight\_g, weight\_source (scale / manual / none), scale\_id, method (marker / ar / manual), confidence (high / medium / low), confidence\_detail (json), divisor\_used, billing\_l/w/h\_cm, cbm, volumetric\_g, chargeable\_g, created\_by, reason |
| `photo` | id, package\_id, version\_id, kind (raw / annotated), storage\_key, width, height, bytes |
| `remeasure_request` | id, shipment\_id, package\_ids\[\], reason, note, status, requested\_by, done\_by, closed\_at |
| `flag` | id, shipment\_id, package\_id, type, status (open / resolved / dismissed), resolved\_by, note |
| `measurement_event` | id, device\_id, user\_id, awb, type (scan, measure\_start, measure\_ready, retake, confirm, manual\_entry, scale\_stable…), payload (json), occurred\_at |
| `audit_log` | id, at, user\_id, role, entity, entity\_id, action, before (json), after (json), reason, ip, device\_id |
| `config` | key, value (json), scope (global / client / branch), scope\_id, updated\_by |

Notes:

- `measurement_event` powers KPIs (measurement time, retake rate, first-pass success) and calibration analysis.
- A package's displayed values always come from its `current_version_id`; versions are never edited or deleted.
- No consignee personal data is stored in any table.

## 13. API overview

One REST API (`/api/v1`) serves mobile, web and future integrations; Claude Code generates the full OpenAPI spec from this list in Milestone 0.

**Conventions:** JWT access token (15 min) + refresh token (12 h); errors as `{code, message, details}`; cursor pagination; `Idempotency-Key` header on every create; times in UTC ISO 8601.

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/change-password` |
| Device | `POST /devices/register` (tier check result), `GET /devices/me/config` |
| Lookup | `GET /awb/{awb}/lookup` (existing MeasureX shipment and packages) |
| Shipments | `GET /shipments`, `GET /shipments/{awb}`, `POST /shipments/{awb}/complete`, `POST /shipments/{awb}/reopen` |
| Packages | `POST /shipments/{awb}/packages` (create, idempotent), `POST /packages/{id}/corrections`, `POST /packages/{id}/void` |
| Photos | `POST /packages/{id}/photos` (returns a signed upload URL), `GET /photos/{id}` (signed view URL) |
| Sync | `POST /sync/batch` (up to 50 packages), `GET /sync/status` |
| Events | `POST /events/batch` |
| Review | `GET /flags`, `POST /flags/{id}/resolve`, `POST /remeasurements`, `POST /remeasurements/{id}/cancel` |
| Admin | CRUD for `/users`, `/branches`, `/clients`, `/stations`, `/scales`, `/devices`, `/config` |
| Reports | \`GET /reports/{type}?format=xlsx |
| Audit | `GET /audit` |
| Integration (later, Phase C) | `GET /ext/shipments/{awb}` and webhook `measurement.completed` for Aymakan systems, API-key auth |

## 14. Tech stack, architecture and security

The stack uses two languages for app code (Dart, TypeScript) plus one C++ vision core, chosen because Claude Code is strong in all three and they are easy to hand over later.

&#91;embedded content: system architecture · 3 clients, 1 API, 4 back-end parts\]

The phone measures and weighs locally, then syncs through the API; nothing outside the API touches the database or Aymakan.

| Layer | Choice |
| --- | --- |
| Mobile app | Flutter (Dart), Riverpod for state, Drift + SQLCipher for the local database, `mobile_scanner` (ML Kit) for barcodes, `flutter_blue_plus` for BLE, a small Kotlin plugin for Bluetooth Classic |
| Measurement engine | C++17 + OpenCV (ArUco module), called through Dart FFI; same code on Android and iOS |
| Backend | Node.js + NestJS (TypeScript), Prisma ORM, PostgreSQL 16 |
| Background jobs | BullMQ + Redis (report exports, photo processing) |
| File storage | S3-compatible object storage, private bucket, signed URLs |
| Web dashboard | React + Next.js (TypeScript), Tailwind, i18n with RTL |
| Repository | One monorepo: `apps/mobile`, `apps/api`, `apps/web`, `packages/measure-core`, `packages/shared` (types, formulas), `docs/` |
| CI/CD | GitHub Actions: tests, lint, builds; Docker images for API and web |
| Monitoring | Sentry (mobile, API, web) for crashes and errors; structured JSON logs |
| Hosting | Cloud region inside Saudi Arabia (A9); managed PostgreSQL, managed Redis, container hosting |
| App distribution | Android: managed Google Play (private app). iOS: Apple Business Manager custom app. TestFlight / internal track for pilots |

**Shared formulas:** CBM, volumetric and chargeable calculations live in one place (`packages/shared`) and are tested against the worked examples; the mobile app shows a preview, the server value is final.

**Security**

- TLS everywhere; passwords hashed with Argon2; JWT with short expiry and refresh rotation.
- Role and branch checks on every endpoint (server side, never only in the UI).
- Photos in a private bucket; access only through short-lived signed URLs; photo views logged.
- Local phone data encrypted and wiped on logout after sync; Admin can block a device.
- Audit log for every create, correction, void, reopen, configuration and user change.
- Data residency and retention per PDPL (A8, A9); no consignee personal data stored outside photos.

## 15. Non-functional requirements and KPIs

Targets are sized for about 2,000 shipments a day with room for 10× growth without redesign.

| Area | Target |
| --- | --- |
| Volume | 2,000 shipments/day now; design for 20,000/day |
| API speed | p95 < 300 ms for lookup and save (excluding photo upload) |
| Scan to camera ready | < 1.5 s on a Standard-tier phone |
| Measurement ready | < 3 s after the box is placed and 2+ markers are visible (start = first marker detected) |
| Full cycle per carton | < 20 s scan to saved (pilot target) |
| Availability | 99.5 % during warehouse hours; capture never stops offline |
| Crash-free sessions | ≥ 99.5 % |
| Accuracy (Phase B target, to confirm in calibration) | Cartons on mat: ≤ 1 cm error per dimension in 90 % of measurements |
| Languages | English, Arabic (RTL), Bengali; Western digits in all languages |
| UI | Primary buttons 56–64 px, touch targets ≥ 48 px, text 16–20 px primary, high contrast, haptic + sound feedback |
| Backups | Daily database backup, 30-day retention; point-in-time recovery |

**KPIs (all computed from `measurement_event` and versions)**

- Operational: shipments and packages per day, per hour, per worker; average full-cycle time.
- Quality: first-pass success, retake rate, confidence distribution, manual-entry rate, correction rate.
- Hardware: scale capture success, device tier mix.
- Technical: sync success without intervention, average sync delay, crash-free sessions.
- Business: weight-discrepancy rate, disputes resolved with photo evidence, chargeable weight added vs declared.

## 16. Delivery plan and milestones

Phase A delivers a usable platform with manual and scale capture; Phase B adds marker-mat measurement once a pilot proves its accuracy; Phase C adds AR and pallets. Each milestone ends with its acceptance criteria passing as automated tests where possible.

&#91;embedded content: delivery roadmap · 3 phases, 2 gates\]

Phase B starts only after the Phase A pilot week; Phase C starts only after the feasibility spike meets its accuracy gate.

**Phase A — platform without camera measurement**

1. **M0 Foundation** — monorepo, CI, `CLAUDE.md`, database schema + migrations, OpenAPI spec, auth, seed data, staging environment.
   - Done when: login works on mobile and web; CI green; OpenAPI published; formulas pass the worked-example tests.
2. **M1 Scan and capture** — scanner with AWB regex, manual AWB, manual dimensions, photo, review, save, multi-piece with Add / Complete, shipment summary.
   - Done when: sections 5–7 happy path and exception paths pass end-to-end.
3. **M2 Scale** — adapter framework, first certified scale (BLE or Classic), HID fallback, stable-weight rule.
   - Done when: section 9 rules pass with real known weights; disconnects never save a value.
4. **M3 Offline and sync** — local encrypted database, queue, provisional numbers, conflicts, photo upload, offline login.
   - Done when: airplane-mode test of 50 packages across 2 devices syncs with no duplicates and correct numbering.
5. **M4 Dashboard and Team Leader tools** — all section 11 pages, corrections, remeasure, review queue, reports, audit, configuration; Team Leader mobile screens.
   - Done when: every action writes the right audit entry; exports open in Excel.
6. **M5 Localisation and pilot** — Arabic RTL, Bengali, device tier check, Sentry, store distribution; pilot at one branch.
   - Done when: one branch runs a full week on MeasureX with manual dimensions.

**Phase B — marker-mat measurement**

7. **B1 Feasibility spike** — C++ core detecting markers and one carton on 3 phone models.
   - Gate: median error ≤ 1 cm on 30 test cartons. If not met, adjust mat or method before continuing.
8. **B2 Integration** — camera screen, live guidance, confidence, annotated photo, mat generator script.
9. **B3 Calibration pilot** — 500+ measurements vs tape at the pilot branch; tune thresholds; publish the accuracy target.

**Phase C — AR and bulky items**

10. **C1** markerless measurement on ARCore/ARKit/LiDAR phones · **C2** pallet floor station · **C3** Aymakan integration (shipment lookup, webhooks, external API).

## 17. Open questions and starting with Claude Code

None of these block Milestone 0; Q1–Q3 must be answered before M1 finishes, Q6 before M2.

- [ ] **Q1** Is AWB-only final until integration, or do reports need a client before then?
- [ ] **Q2** What do the QR code (`AYM0000831`) and the number `3001111028` on the label contain?
- [ ] **Q3** Multi-piece: does each piece carry the same AWB label, or a piece suffix?
- [ ] **Q4** Confirm assumptions A4–A8 (divisor, rounding, weight required, Medium confidence, retention).
- [ ] **Q5** Rough share of daily volume: small cartons vs bulky vs pallets (confirms A10).
- [ ] **Q6** Which scale models do branches already own (brand, model, BLE or Classic)?
- [ ] **Q7** Are scale platforms large enough to hold a mat, or are mat and scale separate?
- [ ] **Q8** Which branch runs the pilot, and which phone models do its workers own?
- [ ] **Q9** Which cloud provider with a Saudi region does Aymakan already use or prefer?

**How to start with Claude Code**

1. Create an empty GitHub repository and open it with Claude Code.
2. Put this PRD in the repo as `docs/PRD.md`.
3. Ask Claude Code to run Milestone 0: write `CLAUDE.md` (stack, folder layout, conventions, "never break these rules"), the database schema, the OpenAPI spec and the decision log from sections 2–14.
4. Review those four files before any feature code is written; they become the contract.
5. Work one milestone at a time: ask for a plan first, then the build, then run the milestone's acceptance tests.
6. Keep shipment data behind the ShipmentSourceAdapter so Aymakan can be added later without touching the app.
