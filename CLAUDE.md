# CLAUDE.md — MeasureX

Build reference for Claude Code. The source of truth for product behaviour is
[`docs/PRD.md`](docs/PRD.md) (Final PRD v2.0). This file captures the stack,
the repo layout, coding conventions, and the rules that must never be broken.
When this file and the PRD disagree, the PRD wins — update this file to match.

## What MeasureX is

An internal Aymakan tool for warehouse workers to dimension and weigh shipments
with a BYOD phone, a printed ArUco marker mat and a Bluetooth scale, saving
every result with a photo and a full audit trail. Delivered in phases: Phase A
(platform with manual + scale capture), Phase B (marker-mat measurement),
Phase C (AR + pallets + Aymakan integration). We are currently in **Milestone 0
(Foundation)**.

## Stack

| Layer              | Choice                                                                                                                           |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Mobile app         | Flutter (Dart), Riverpod, Drift + SQLCipher, `mobile_scanner` (ML Kit), `flutter_blue_plus`, Kotlin plugin for Bluetooth Classic |
| Measurement engine | C++17 + OpenCV (ArUco), called via Dart FFI; one codebase for Android + iOS                                                      |
| Backend API        | Node.js + NestJS (TypeScript), Prisma ORM, PostgreSQL 16                                                                         |
| Background jobs    | BullMQ + Redis (report exports, photo processing)                                                                                |
| File storage       | S3-compatible object storage, private bucket, signed URLs only                                                                   |
| Web dashboard      | React + Next.js (TypeScript), Tailwind, i18n with RTL                                                                            |
| Shared logic       | `packages/shared` — TypeScript types + billing formulas (CBM, volumetric, chargeable)                                            |
| CI/CD              | GitHub Actions: lint, tests, builds; Docker images for API and web                                                               |
| Monitoring         | Sentry (mobile, API, web); structured JSON logs                                                                                  |
| Hosting            | Cloud region inside Saudi Arabia (PDPL); managed Postgres + Redis                                                                |

**Languages in the codebase:** Dart, TypeScript, C++17. Keep the surface small
and well documented — there is no in-house dev team; Claude Code builds and the
project must stay easy to hand over.

## Monorepo layout

```
measurex/
├── apps/
│   ├── mobile/          # Flutter app (Labour + Team Leader)
│   ├── api/             # NestJS REST API (/api/v1)
│   └── web/             # Next.js dashboard (Team Leader + Admin)
├── packages/
│   ├── measure-core/    # C++17 + OpenCV vision core (FFI)
│   └── shared/          # TS types + billing formulas (single source of truth)
├── docs/
│   ├── PRD.md           # Product requirements (v2.0) — source of truth
│   ├── DECISIONS.md     # Decision log (PRD §2–14)
│   ├── schema/          # Pointer → apps/api/prisma/schema.prisma (data model, §12)
│   └── openapi.yaml     # Full API spec (PRD §13)
├── .github/workflows/   # CI
├── docker-compose.yml   # Postgres + Redis for local dev
└── CLAUDE.md
```

Tooling: **pnpm workspaces** for the TS/JS packages (`apps/api`, `apps/web`,
`packages/shared`). `apps/mobile` uses pub; `packages/measure-core` uses CMake.

## Coding conventions

- **TypeScript is strict** (`strict: true`, no implicit `any`). Prefer explicit
  return types on exported functions.
- **Base units are integers.** Dimensions in millimetres, weight in grams,
  always `number`-as-integer. Never store or persist floats for base units.
- **Billing math lives in exactly one place:** `packages/shared`. The mobile app
  and the API both import it; nobody re-implements a formula. Server output is
  final; mobile renders a preview.
- **Money/measurement rounding** follows PRD §7 exactly (dimensions ceil to the
  next cm; chargeable weight rounds up to the configured step, default 0.5 kg).
- **Naming:** `camelCase` for TS vars/functions, `PascalCase` for types/classes,
  `snake_case` for database columns (Prisma maps via `@map`).
- **Every TS/JS package has tests** (Vitest) and passes lint before merge.
- **Times are UTC ISO 8601** across API, DB and logs.
- **IDs are UUIDs.** Packages use a client-generated UUID + idempotency key.
- Keep functions pure where possible; isolate side effects (DB, network, FFI).

## Never break these rules

These come straight from the PRD and are non-negotiable for any milestone:

1. **Integer base units.** Store dimensions in **mm** and weight in **g** as
   integers. No floats for base units, ever. (PRD §7, §12)
2. **Server is final for calculations.** All billing figures (billing L/W/H,
   CBM, volumetric, chargeable) and all package numbers are computed and
   assigned on the server. Mobile shows a preview only and must never persist a
   value as authoritative. (PRD §7, §10)
3. **Audit on every change.** Every create, correction, void, reopen,
   configuration change and user change writes an `audit_log` entry
   (before/after/reason). Measurement versions are never edited or deleted;
   corrections create a new version and keep the old one. (PRD §8, §11, §14)
4. **No consignee personal data.** Never store consignee name, phone or address
   in any table. Personal data exists only inside the label photo, which is
   private (signed URLs), role-restricted and retention-limited. (PRD §6, §12)
5. **AWB-only capture, no Aymakan integration.** The worker scans only the AWB
   (`^AY\d{11}$`, configurable). No client, piece count or declared weight is
   entered or fetched. All shipment data sits behind a backend
   `ShipmentSourceAdapter` so Aymakan can be connected later without changing
   the app. Do not add an Aymakan client/integration in Phases A–B. (PRD §1,
   §6, §17)
6. **Security + access on the server.** Role and branch checks on every
   endpoint, server-side (never only in the UI). Photos only via short-lived
   signed URLs; local phone data encrypted (SQLCipher) and wiped on logout once
   synced. Soft delete only. (PRD §10, §14)

## Milestone 0 scope (current)

Foundation only — **no feature code yet**: monorepo + CI, this `CLAUDE.md`,
the Prisma schema, the OpenAPI spec, the decision log, and the shared formula
package with tests. Done when: the formulas pass the worked-example tests and
CI is green. Feature work (scanner, capture, scale, sync, dashboard) begins at
M1 and later, one milestone at a time, plan first.
