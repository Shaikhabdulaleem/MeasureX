-- M4: package numbers are unique only among LIVE, ACTIVE packages.
--
-- A remeasurement (PRD §8) keeps the superseded old package row and creates a
-- new active row that REUSES the same package_number. The original
-- table-wide UNIQUE(shipment_id, package_number) forbade that. Replace it with
-- a PARTIAL unique index scoped to active, non-deleted packages, so:
--   * a superseded row and the active row that replaced it can share a number;
--   * a voided row keeps its number reserved (renumberByConfirmedAt excludes it)
--     without blocking the active sequence;
--   * two active packages in a shipment still can never share a number.
--
-- Prisma cannot express a WHERE clause on @@unique, so this is raw SQL. The
-- schema keeps a plain @@index([shipmentId, packageNumber]) for lookups.

-- Drop the old table-wide unique index.
DROP INDEX IF EXISTS "package_shipment_id_package_number_key";

-- Plain composite index for lookups (matches @@index in schema.prisma).
CREATE INDEX IF NOT EXISTS "package_shipment_id_package_number_idx"
  ON "package"("shipment_id", "package_number");

-- Partial unique: only live, active packages compete for a number. The name
-- keeps the "package_number" token so the lost-race detector
-- (isPackageNumberConflict in packages.service.ts) still recognises a P2002 on
-- this index by its target name.
CREATE UNIQUE INDEX "package_active_shipment_package_number_key"
  ON "package"("shipment_id", "package_number")
  WHERE "status" = 'active' AND "deleted_at" IS NULL;
