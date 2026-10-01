# MeasureX

Internal Aymakan app for dimensioning and weighing shipments on a BYOD phone,
with a web dashboard and a server that is the final authority on every
calculation. Build reference: [`docs/PRD.md`](docs/PRD.md). Conventions and the
non-negotiable rules live in [`CLAUDE.md`](CLAUDE.md).

**Status:** Milestone 0 (Foundation) — monorepo, CI, schema + migration,
OpenAPI, shared formulas, auth (login / refresh / logout / change-password with
forced first-login change, 5-attempt lockout, audit), a web login + dashboard
skeleton, and a mobile login + home skeleton. Feature capture begins at M1.

## Layout

```
apps/mobile   Flutter app (Labour + Team Leader)
apps/api      NestJS API (/api/v1)
apps/web      Next.js dashboard
packages/shared        TS billing formulas (single source of truth)
packages/measure-core  C++ vision core (Phase B)
docs          PRD, decisions, OpenAPI; schema lives in apps/api/prisma
```

## Prerequisites

- Node 20+ and **pnpm 9** (`corepack enable` provides it)
- Docker + Docker Compose (Postgres + Redis)
- Flutter 3.4+ (for the mobile app)

## 1. Infrastructure

```bash
cp .env.example .env            # optional; compose has sane defaults
docker compose up -d            # Postgres :5432, Redis :6379
```

## 2. API

```bash
pnpm install
cp apps/api/.env.example apps/api/.env
pnpm --filter @measurex/api prisma:generate
pnpm --filter @measurex/api prisma:migrate        # apply migrations
pnpm --filter @measurex/api db:seed               # branch, users, config
pnpm --filter @measurex/api start:dev             # http://localhost:3000/api/v1
```

Health check: `GET http://localhost:3000/api/v1/health`.

**Seeded logins** (all start with a forced password change on first login):

| Employee ID | Role | Initial password |
| --- | --- | --- |
| `ADMIN001` | admin | `ChangeMe123!` |
| `TL001` | team_leader | `ChangeMe123!` |
| `LAB001` | labour | `ChangeMe123!` |
| `LAB002` | labour | `ChangeMe123!` |

## 3. Web dashboard

```bash
cp apps/web/.env.example apps/web/.env.local       # NEXT_PUBLIC_API_URL
pnpm --filter @measurex/web dev                     # http://localhost:3001
```

Sign in with a seeded user; you'll be prompted to set a new password, then land
on the dashboard showing your name and role. Toggle English/Arabic (RTL) from
the top-right button.

## 4. Mobile app

See [`apps/mobile/README.md`](apps/mobile/README.md) for first-time setup
(`flutter create .` to scaffold platform folders, and enabling cleartext HTTP
for local dev). Then:

```bash
cd apps/mobile
flutter pub get
flutter run                                          # emulator → API at 10.0.2.2
# physical phone on the same Wi-Fi:
flutter run --dart-define=API_URL=http://<your-pc-ip>:3000/api/v1
```

## Checks (what CI runs)

```bash
pnpm format        # prettier --check
pnpm lint          # eslint
pnpm typecheck     # tsc --noEmit (all TS workspaces)
pnpm test          # shared formulas (vitest) + API auth suite (jest, needs DB)
```

The API test suite needs `DATABASE_URL` pointing at a running Postgres
(docker compose covers this locally; CI runs a Postgres service). Flutter
`analyze` + `test` run in a separate CI job.
