import { Injectable } from '@nestjs/common';
import { Role } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';

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
}

function toJson(value: unknown): object | undefined {
  if (value === undefined || value === null) return undefined;
  return value as object;
}
