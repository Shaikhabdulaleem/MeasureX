import { Prisma } from '@prisma/client';
import { AuthUser } from '../auth/decorators/current-user.decorator';

/** Labour history window: own measurements, last 7 days (PRD §3). */
export const LABOUR_HISTORY_DAYS = 7;

/** A `where` fragment that matches no shipment (fail-closed). */
export const MATCH_NONE: Prisma.ShipmentWhereInput = { id: { in: [] } };

/**
 * Prisma `where` fragment restricting shipments to what a user may see
 * (PRD §3). Enforced server-side on every shipment read — never in the UI only.
 *
 *  - admin  : all branches only when adminScope = "all"; otherwise the scoped
 *             branch ids. An admin with NO scope (null/empty) sees nothing —
 *             access is fail-closed, never "everything".
 *  - team_leader : own home branch
 *  - labour : shipments that carry a package they measured, within 7 days
 */
export function shipmentScopeWhere(user: AuthUser): Prisma.ShipmentWhereInput {
  if (user.role === 'admin') {
    if (user.adminScope === 'all') return {};
    const branchIds = Array.isArray(user.adminScope) ? user.adminScope : [];
    if (branchIds.includes('all')) return {};
    if (branchIds.length === 0) return MATCH_NONE; // null or empty scope → no access
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

/**
 * Whether a user may ADD a package to a shipment that belongs to `branchId`
 * (PRD §3). Same home branch is always allowed; a different branch is allowed
 * only for an admin whose scope includes it (or "all"). Team leaders and labour
 * are confined to their home branch.
 */
export function canAccessBranch(user: AuthUser, branchId: string | null): boolean {
  if (branchId == null) return true; // legacy/unscoped shipment
  if (branchId === user.homeBranchId) return true;
  if (user.role === 'admin') {
    if (user.adminScope === 'all') return true;
    if (Array.isArray(user.adminScope)) {
      return user.adminScope.includes('all') || user.adminScope.includes(branchId);
    }
  }
  return false;
}
