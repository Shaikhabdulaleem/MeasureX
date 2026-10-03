import { Injectable } from '@nestjs/common';
import { AuditLog, Prisma, Role } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';

export interface AuditInput {
  userId?: string | null;
  role?: Role | null;
  entity: string;
  entityId?: string | null;
  action: string;
  before?: unknown;
  after?: unknown;
  reason?: string | null;
  ip?: string | null;
  deviceId?: string | null;
}

/**
 * Writes an `audit_log` row. Every auth event (login success/fail, lockout,
 * logout, password change) goes through here — see CLAUDE.md rule 3.
 */
@Injectable()
export class AuditService {
  constructor(private readonly prisma: PrismaService) {}

  async record(input: AuditInput): Promise<void> {
    await this.prisma.auditLog.create({
      data: {
        userId: input.userId ?? null,
        role: input.role ?? null,
        entity: input.entity,
        entityId: input.entityId ?? null,
        action: input.action,
        before: toJson(input.before),
        after: toJson(input.after),
        reason: input.reason ?? null,
        ip: input.ip ?? null,
        deviceId: input.deviceId ?? null,
      },
    });
  }

  /**
   * GET /audit — the audit log, scoped and filtered (PRD §11, §14). An Admin
   * with "all" scope sees every entry; a Team Leader or scoped Admin sees
   * entries whose ACTOR belongs to a branch in their scope (so a branch's own
   * activity, including corrections/voids/reopens/remeasures by their staff,
   * while Admin-only changes like users/config stay out of a Team Leader's
   * view). Cursor-paginated, newest first.
   */
  async list(user: AuthUser, query: AuditQuery) {
    const limit = Math.min(Number(query.limit) || 50, 200);
    const and: Prisma.AuditLogWhereInput[] = [this.scopeWhere(user)];
    if (query.entity) and.push({ entity: query.entity });
    if (query.entityId) and.push({ entityId: query.entityId });
    if (query.action) and.push({ action: query.action });
    if (query.userId) and.push({ userId: query.userId });
    if (query.dateFrom || query.dateTo) {
      and.push({
        at: {
          ...(query.dateFrom ? { gte: new Date(query.dateFrom) } : {}),
          ...(query.dateTo ? { lte: new Date(query.dateTo) } : {}),
        },
      });
    }

    const rows = await this.prisma.auditLog.findMany({
      where: { AND: and },
      orderBy: [{ at: 'desc' }, { id: 'desc' }],
      take: limit + 1,
      ...(query.cursor ? { cursor: { id: query.cursor }, skip: 1 } : {}),
    });

    const hasMore = rows.length > limit;
    const page = hasMore ? rows.slice(0, limit) : rows;
    return {
      items: page.map(serializeAudit),
      nextCursor: hasMore ? page[page.length - 1]!.id : null,
    };
  }

  /** Actor-branch scope: admins with "all" see everything; others see their branches' actors. */
  private scopeWhere(user: AuthUser): Prisma.AuditLogWhereInput {
    if (user.role === 'admin') {
      if (user.adminScope === 'all') return {};
      const ids = Array.isArray(user.adminScope) ? user.adminScope : [];
      if (ids.includes('all')) return {};
      if (ids.length === 0) return { id: { in: [] } };
      return { user: { is: { homeBranchId: { in: ids } } } };
    }
    // team_leader: own branch's actors. (Labour has no audit access — guarded.)
    return { user: { is: { homeBranchId: user.homeBranchId } } };
  }
}

export interface AuditQuery {
  entity?: string;
  entityId?: string;
  action?: string;
  userId?: string;
  dateFrom?: string;
  dateTo?: string;
  cursor?: string;
  limit?: string;
}

function serializeAudit(a: AuditLog) {
  return {
    id: a.id,
    at: a.at.toISOString(),
    userId: a.userId,
    role: a.role,
    entity: a.entity,
    entityId: a.entityId,
    action: a.action,
    before: a.before ?? null,
    after: a.after ?? null,
    reason: a.reason,
    deviceId: a.deviceId,
  };
}

function toJson(value: unknown): object | undefined {
  if (value === undefined || value === null) return undefined;
  return value as object;
}
