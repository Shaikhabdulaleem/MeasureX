import { Prisma } from '@prisma/client';

/** A Prisma client or an interactive-transaction client. */
export type Db = Prisma.TransactionClient;

/**
 * Recompute and persist a shipment's denormalised totals from its ACTIVE
 * packages' current versions (PRD §7: "sum of active packages, recomputed on
 * every change"). Voided and superseded packages are excluded. Call inside the
 * same transaction that changed a package.
 */
export async function recomputeShipmentTotals(db: Db, shipmentId: string): Promise<void> {
  const packages = await db.package.findMany({
    where: { shipmentId, status: 'active', deletedAt: null },
    include: { currentVersion: true },
  });

  let pieces = 0;
  let cbm = new Prisma.Decimal(0);
  let actualG = 0;
  let volumetricG = 0;
  let chargeableG = 0;

  for (const pkg of packages) {
    const v = pkg.currentVersion;
    if (!v) continue;
    pieces += 1;
    cbm = cbm.add(v.cbm);
    actualG += v.actualWeightG ?? 0;
    volumetricG += v.volumetricG;
    chargeableG += v.chargeableG;
  }

  await db.shipment.update({
    where: { id: shipmentId },
    data: {
      totalPieces: pieces,
      totalCbm: cbm,
      totalActualG: actualG,
      totalVolumetricG: volumetricG,
      totalChargeableG: chargeableG,
    },
  });
}
