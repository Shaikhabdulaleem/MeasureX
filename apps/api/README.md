# apps/api

NestJS (TypeScript) REST API serving `/api/v1` to mobile, web and future
integrations. **Skeleton only** in Milestone 0.

- Contract: [`../../docs/openapi.yaml`](../../docs/openapi.yaml).
- Data model: [`prisma/schema.prisma`](prisma/schema.prisma) (the canonical
  schema; `docs/schema/` points here).
- Billing math comes from `@measurex/shared`; the server is the final authority
  on all calculations and package numbers (root `CLAUDE.md`).
- Background jobs: BullMQ + Redis. Storage: S3-compatible private bucket.

## What's implemented (Milestone 0)

Auth only: `POST /auth/login`, `/auth/refresh`, `/auth/logout`,
`/auth/change-password`, plus `GET /health`. Argon2 passwords, JWT access
(15 min) + refresh (12 h) with rotation, forced first-login password change,
5-attempt / 15-minute lockout, a server-side role guard, and an `audit_log`
entry on every auth event. Everything else in `openapi.yaml` lands in M1+.

## Run locally

From the repo root with Docker Postgres up (see root `README.md`):

```bash
pnpm --filter @measurex/api prisma:generate
pnpm --filter @measurex/api prisma:migrate:dev   # applies migrations
pnpm --filter @measurex/api db:seed              # seed users + config
pnpm --filter @measurex/api start:dev            # http://localhost:3000
```

Tests (`pnpm --filter @measurex/api test`) run against a Postgres pointed to by
`DATABASE_URL`.
