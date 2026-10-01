import { Prisma } from '@prisma/client';
import { AuthUser } from '../auth/decorators/current-user.decorator';

/** Labour history window: own measurements, last 7 days (PRD §3). */
export const LABOUR_HISTORY_DAYS = 7;

/**
 * Prisma `where` fragment restricting shipments to what a user may see
 * (PRD §3). Enforced server-side on every shipment read — never in the UI only.
 *
 *  - admin  : scoped branches, or all branches when adminScope = "all"
 *  - team_leader : own home branch
 *  - labour : shipments that carry a package they measured, within 7 days
 */
export function shipmentScopeWhere(user: AuthUser): Prisma.ShipmentWhereInput {
  if (user.role === 'admin') {
    if (user.adminScope === 'all' || user.adminScope === null) return {};
    const branchIds = Array.isArray(user.adminScope) ? user.adminScope : [];
    if (branchIds.includes('all')) return {};
    return { branchId: { in: branchIds } };
  }

  if (user.role === 'team_leader') {
    return { branchId: user.homeBranchId };
  }

  // labour
  const since = new Date(Date.now() - LABOUR_HISTORY_DAYS * 24 * 60 * 60 * 1000);
  return {
    packages: {
      some: { measuredBy: user.sub, confirmedAt: { gte: since } },
    },
  };
}
