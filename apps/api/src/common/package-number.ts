/**
 * Next package number for a shipment (PRD §7: "highest number + 1"; the server
 * is final). Computed over ALL non-deleted packages regardless of status so a
 * voided package never has its number reused (that would break the
 * (shipment, package_number) uniqueness). Voided packages are excluded from
 * totals elsewhere, not from numbering.
 */
export function nextPackageNumber(packages: Array<{ packageNumber: number | null }>): number {
  let max = 0;
  for (const p of packages) {
    if (p.packageNumber != null && p.packageNumber > max) max = p.packageNumber;
  }
  return max + 1;
}
