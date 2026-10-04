import { Prisma } from '@prisma/client';

/**
 * Next package number for a shipment (PRD §7: "highest number + 1"; the server
 * is final). Computed over ALL non-deleted packages regardless of status so a
 * voided package never has its number reused (that would break the
 * (shipment, package_number) uniqueness). Voided packages are excluded from
 * totals elsewhere, not from numbering.
 *
 * Used as a provisional hint (e.g. the lookup endpoint's `nextPackageNumber`);
 * the authoritative assignment is {@link renumberByConfirmedAt}.
 */
export function nextPackageNumber(packages: Array<{ packageNumber: number | null }>): number {
  let max = 0;
  for (const p of packages) {
    if (p.packageNumber != null && p.packageNumber > max) max = p.packageNumber;
  }
  return max + 1;
}

/** A package number that changed during a renumber, for auditing. */
export interface RenumberChange {
  id: string;
  from: number | null;
  to: number;
}

/**
 * Assign authoritative package numbers for a shipment in `confirmed_at` order
 * (PRD §10 rule 2: "On sync the server assigns final numbers in order of
 * confirmed_at"). Active, non-deleted packages are numbered 1..N by
 * (confirmedAt ASC, id ASC). Voided/superseded packages keep their number so it
 * is never reused.
 *
 * For online, in-order creates this produces the same result as max+1, so the
 * single-create path is unchanged in the common case; it only corrects
 * out-of-order offline arrivals.
 *
 * Remeasurement interaction (PRD §8): a remeasured package becomes `superseded`
 * and its number is taken over by the new `active` replacement that shares it.
 * So a superseded number is NOT reserved on its own — it is held by its active
 * replacement, which is PINNED: it keeps its number and is never moved by a
 * renumber. Only UNPINNED active packages are resequenced, skipping the numbers
 * held by voided packages and by pinned replacements. (A superseded package
 * whose replacement was later voided keeps its number out of the sequence via
 * that void.)
 *
 * Done in two phases because of the active-package unique index: phase 1 nulls
 * the numbers of the rows we are about to reassign (Postgres treats multiple
 * NULLs as distinct, so no clash), phase 2 writes the final sequential numbers.
 * Call inside the per-AWB advisory-locked transaction.
 *
 * Returns the set of genuine changes so the caller can audit them.
 */
export async function renumberByConfirmedAt(
  tx: Prisma.TransactionClient,
  shipmentId: string,
): Promise<RenumberChange[]> {
  const active = await tx.package.findMany({
    where: { shipmentId, status: 'active', deletedAt: null },
    select: { id: true, packageNumber: true, confirmedAt: true },
    orderBy: [{ confirmedAt: 'asc' }, { id: 'asc' }],
  });

  // Numbers taken over by a remeasurement: a superseded package's number is
  // held by its active replacement. These are NOT reserved by themselves —
  // the replacement (an active package below) pins the number.
  const superseded = await tx.package.findMany({
    where: { shipmentId, deletedAt: null, status: 'superseded', packageNumber: { not: null } },
    select: { packageNumber: true },
  });
  const supersededNumbers = new Set(superseded.map((p) => p.packageNumber as number));

  // Voided numbers stay out of the active sequence (PRD §8).
  const voided = await tx.package.findMany({
    where: { shipmentId, deletedAt: null, status: 'void', packageNumber: { not: null } },
    select: { packageNumber: true },
  });
  const voidedNumbers = new Set(voided.map((p) => p.packageNumber as number));

  // A PINNED active package is a remeasurement replacement: active, numbered,
  // and sharing its number with a superseded package. It keeps its number and
  // is excluded from the resequence.
  const isPinned = (p: { packageNumber: number | null }): boolean =>
    p.packageNumber != null && supersededNumbers.has(p.packageNumber);

  const pinnedNumbers = new Set(active.filter(isPinned).map((p) => p.packageNumber as number));

  // Unpinned active packages are resequenced around voided + pinned numbers.
  const reservedNumbers = new Set<number>([...voidedNumbers, ...pinnedNumbers]);
  const unpinned = active.filter((p) => !isPinned(p));

  let candidate = 0;
  const nextFree = (): number => {
    do {
      candidate += 1;
    } while (reservedNumbers.has(candidate));
    return candidate;
  };

  const changes: RenumberChange[] = [];
  for (const pkg of unpinned) {
    const target = nextFree();
    if (pkg.packageNumber !== target) {
      changes.push({ id: pkg.id, from: pkg.packageNumber, to: target });
    }
  }

  if (changes.length === 0) return changes;

  // Phase 1: clear the numbers of every row that is moving, so phase 2 can
  // write final values without transiently colliding on the unique index.
  await tx.package.updateMany({
    where: { id: { in: changes.map((c) => c.id) } },
    data: { packageNumber: null },
  });

  // Phase 2: write the final sequential numbers.
  for (const change of changes) {
    await tx.package.update({
      where: { id: change.id },
      data: { packageNumber: change.to },
    });
  }

  return changes;
}
