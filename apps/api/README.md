# apps/api

NestJS (TypeScript) REST API serving `/api/v1` to mobile, web and future
integrations. **Skeleton only** in Milestone 0.

- Contract: [`../../docs/openapi.yaml`](../../docs/openapi.yaml).
- Data model: [`prisma/schema.prisma`](prisma/schema.prisma) (the canonical
  schema; `docs/schema/` points here).
- Billing math comes from `@measurex/shared`; the server is the final authority
  on all calculations and package numbers (root `CLAUDE.md`).
- Background jobs: BullMQ + Redis. Storage: S3-compatible private bucket.

## What's implemented

**Milestone 0 — auth:** `POST /auth/login`, `/auth/refresh`, `/auth/logout`,
`/auth/change-password`, `GET /health`. Argon2 passwords, JWT access (15 min) +
refresh (12 h) with rotation, forced first-login password change, 5-attempt /
15-minute lockout, a server-side role guard, and an `audit_log` entry on every
auth event.

**Milestone 1 — scan & capture:**

- `GET /awb/{awb}/lookup` — cross-device history check (AWB validated against the
  configured regex; `found=false` for a new AWB).
- `POST /shipments/{awb}/packages` — idempotent (client UUID + `Idempotency-Key`).
  Creates the shipment on the first package, assigns the package number, computes
  billing with `@measurex/shared`, writes `audit_log`.
- `GET /shipments`, `GET /shipments/{awb}` — scoped + filtered.
- `POST /shipments/{awb}/complete` — state machine `in_progress → completed`;
  idle shipments auto-complete after 30 min (BullMQ, configurable).
- `POST /packages/{id}/photos` (signed upload URL) and `GET /photos/{id}` (signed
  view URL, Team Leader/Admin only, logged).
- `POST /flags` and `POST /remeasurements` (+ cancel) — M1 "buttons" only.
- `GET /devices/me/config`, `POST /devices/register`.

Weight is captured from M2 (`weight_source=none`, `actual_weight_required=false`).

## Run locally

From the repo root with Docker infra up (`docker compose up -d` →
Postgres + Redis + MinIO; see root `README.md`):

```bash
pnpm --filter @measurex/api prisma:generate
pnpm --filter @measurex/api prisma:migrate:dev   # applies migrations
pnpm --filter @measurex/api db:seed              # seed users + config
pnpm --filter @measurex/shared build             # shared formulas → dist (runtime)
pnpm --filter @measurex/api start:dev            # http://localhost:3000
```

Local defaults target MinIO at `http://localhost:9000` (bucket `measurex-photos`,
created on boot) and Redis at `redis://localhost:6379` (`REDIS_URL`; unset =
scheduler disabled). See `.env.example`.

Tests (`pnpm --filter @measurex/api test`) run against a Postgres pointed to by
`DATABASE_URL` and need neither Redis nor MinIO (the scheduler self-disables and
photo URL signing is offline).
