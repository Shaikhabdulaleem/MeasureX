# docs/schema

The Prisma schema now lives with the API, at
[`apps/api/prisma/schema.prisma`](../../apps/api/prisma/schema.prisma), where it
is wired to the datasource and drives migrations.

It was moved here in Milestone 0 once backend work began. The data model is
documented in [`../PRD.md`](../PRD.md) §12; this directory is kept as a stable
pointer for anyone looking for "the schema" under `docs/`.
