# apps/api

NestJS (TypeScript) REST API serving `/api/v1` to mobile, web and future
integrations. **Skeleton only** in Milestone 0.

- Contract: [`../../docs/openapi.yaml`](../../docs/openapi.yaml).
- Data model: [`../../docs/schema/schema.prisma`](../../docs/schema/schema.prisma)
  (copied into this app and wired to a datasource when backend work begins).
- Billing math comes from `@measurex/shared`; the server is the final authority
  on all calculations and package numbers (root `CLAUDE.md`).
- Background jobs: BullMQ + Redis. Storage: S3-compatible private bucket.

Auth, migrations and seed data are the first M0/M1 backend deliverables.
