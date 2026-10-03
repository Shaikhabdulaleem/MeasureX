import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Flag, Prisma, RemeasureRequest } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { shipmentScopeWhere } from '../common/scope';
import { FlagCreateDto, FlagQueryDto, FlagResolveDto, RemeasureCreateDto } from './dto/review.dto';

const DEFAULT_LIMIT = 50;

@Injectable()
export class ReviewService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /**
   * Create a flag. Used by the Labour "Flag for Team Leader" button (worker_flag)
   * on a completed shipment. The flag type is also added to the shipment's
   * `flags` array so it surfaces on the dashboard (PRD §5, §11). Full triage of
   * flags is M4.
   */
  async createFlag(dto: FlagCreateDto, user: AuthUser, ip?: string) {
    if (!dto.shipmentId && !dto.packageId) {
      throw new BadRequestException({
        code: 'TARGET_REQUIRED',
        message: 'A flag needs a shipmentId or packageId',
      });
    }

    const type = dto.type ?? 'worker_flag';

    if (dto.shipmentId) {
      const shipment = await this.prisma.shipment.findFirst({
        where: { id: dto.shipmentId, deletedAt: null },
        select: { id: true, flags: true },
      });
      if (!shipment) {
        throw new NotFoundException({ code: 'NOT_FOUND', message: 'Shipment not found' });
      }
      if (!shipment.flags.includes(type)) {
        await this.prisma.shipment.update({
          where: { id: shipment.id },
          data: { flags: { set: [...shipment.flags, type] } },
        });
      }
    }

    const flag = await this.prisma.flag.create({
      data: {
        shipmentId: dto.shipmentId ?? null,
        packageId: dto.packageId ?? null,
        type,
        status: 'open',
        note: dto.note ?? null,
      },
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'flag',
      entityId: flag.id,
      action: 'flag_created',
      after: serializeFlag(flag),
      reason: dto.note ?? null,
      ip,
    });

    return serializeFlag(flag);
  }

  /**
   * Request a remeasurement: creates the request and moves the shipment
   * completed → remeasure_required (PRD §8). The remeasure-completion loop and
   * TL review UI are M4.
   */
  async createRemeasure(dto: RemeasureCreateDto, user: AuthUser, ip?: string) {
    if (dto.reason === 'other' && !dto.note?.trim()) {
      throw new BadRequestException({
        code: 'NOTE_REQUIRED',
        message: 'A note is required when reason is "other"',
      });
    }

    const shipment = await this.prisma.shipment.findFirst({
      where: { id: dto.shipmentId, deletedAt: null },
    });
    if (!shipment) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Shipment not found' });
    }
    if (shipment.status !== 'completed') {
      throw new ConflictException({
        code: 'INVALID_TRANSITION',
        message: `Remeasurement can only be requested on a completed shipment`,
        details: { from: shipment.status, to: 'remeasure_required' },
      });
    }

    const request = await this.prisma.$transaction(async (tx) => {
      const created = await tx.remeasureRequest.create({
        data: {
          shipmentId: dto.shipmentId,
          packageIds: dto.packageIds,
          reason: dto.reason,
          note: dto.note ?? null,
          status: 'open',
          requestedBy: user.sub,
        },
      });
      await tx.shipment.update({
        where: { id: shipment.id },
        data: { status: 'remeasure_required' },
      });
      return created;
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'shipment',
      entityId: shipment.id,
      action: 'remeasure_requested',
      before: { status: shipment.status },
      after: { status: 'remeasure_required', requestId: request.id },
      reason: dto.reason,
      ip,
    });

    return serializeRemeasure(request);
  }

  /**
   * GET /flags — the Team-Leader review queue (PRD §11), branch-scoped. Returns
   * flags whose shipment (directly, or via the flagged package) is in the
   * caller's scope. Cursor-paginated, newest first.
   */
  async listFlags(user: AuthUser, query: FlagQueryDto) {
    const limit = Math.min(Number(query.limit) || DEFAULT_LIMIT, 100);
    const scope = shipmentScopeWhere(user);

    const and: Prisma.FlagWhereInput[] = [
      { deletedAt: null },
      {
        OR: [
          { shipment: { is: scope } },
          { AND: [{ shipmentId: null }, { package: { is: { shipment: { is: scope } } } }] },
        ],
      },
    ];
    if (query.status) and.push({ status: query.status });
    if (query.type) and.push({ type: query.type });
    if (query.awb) {
      and.push({ shipment: { is: { awb: { contains: query.awb.toUpperCase() } } } });
    }

    const rows = await this.prisma.flag.findMany({
      where: { AND: and },
      orderBy: [{ createdAt: 'desc' }, { id: 'desc' }],
      take: limit + 1,
      ...(query.cursor ? { cursor: { id: query.cursor }, skip: 1 } : {}),
      include: { shipment: { select: { awb: true, branchId: true } } },
    });

    const hasMore = rows.length > limit;
    const page = hasMore ? rows.slice(0, limit) : rows;
    return {
      items: page.map((f) => ({ ...serializeFlag(f), awb: f.shipment?.awb ?? null })),
      nextCursor: hasMore ? page[page.length - 1]!.id : null,
    };
  }

  /**
   * GET /remeasurements — open (and recent) remeasurement requests in the
   * caller's scope (PRD §11). Cursor-paginated, newest first.
   */
  async listRemeasurements(user: AuthUser, status: string | undefined, cursor?: string) {
    const scope = shipmentScopeWhere(user);
    const and: Prisma.RemeasureRequestWhereInput[] = [
      { deletedAt: null },
      { shipment: { is: scope } },
    ];
    if (status === 'open' || status === 'done' || status === 'cancelled') {
      and.push({ status });
    }

    const rows = await this.prisma.remeasureRequest.findMany({
      where: { AND: and },
      orderBy: [{ createdAt: 'desc' }, { id: 'desc' }],
      take: 51,
      ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
      include: { shipment: { select: { awb: true } } },
    });

    const hasMore = rows.length > 50;
    const page = hasMore ? rows.slice(0, 50) : rows;
    return {
      items: page.map((r) => ({ ...serializeRemeasure(r), awb: r.shipment?.awb ?? null })),
      nextCursor: hasMore ? page[page.length - 1]!.id : null,
    };
  }

  /**
   * POST /flags/{id}/resolve — approve or dismiss a flag (PRD §11). Both close
   * the flag (status resolved / dismissed) with an optional note; when no open
   * flag of that type remains on the shipment, the type is removed from the
   * shipment's `flags[]` summary. Branch-scoped and audited.
   */
  async resolveFlag(id: string, dto: FlagResolveDto, user: AuthUser, ip?: string) {
    const scope = shipmentScopeWhere(user);
    const flag = await this.prisma.flag.findFirst({
      where: {
        id,
        deletedAt: null,
        OR: [
          { shipment: { is: scope } },
          { AND: [{ shipmentId: null }, { package: { is: { shipment: { is: scope } } } }] },
        ],
      },
    });
    if (!flag) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Flag not found' });
    }
    if (flag.status !== 'open') {
      throw new ConflictException({
        code: 'FLAG_NOT_OPEN',
        message: `Flag is already ${flag.status}`,
      });
    }

    const newStatus = dto.action === 'approve' ? 'resolved' : 'dismissed';

    const updated = await this.prisma.$transaction(async (tx) => {
      const u = await tx.flag.update({
        where: { id },
        data: { status: newStatus, resolvedBy: user.sub, note: dto.note ?? flag.note },
      });

      // Prune the shipment summary when no open flag of this type remains.
      if (flag.shipmentId) {
        const stillOpen = await tx.flag.count({
          where: { shipmentId: flag.shipmentId, type: flag.type, status: 'open', deletedAt: null },
        });
        if (stillOpen === 0) {
          const shipment = await tx.shipment.findUnique({
            where: { id: flag.shipmentId },
            select: { flags: true },
          });
          if (shipment?.flags.includes(flag.type)) {
            await tx.shipment.update({
              where: { id: flag.shipmentId },
              data: { flags: { set: shipment.flags.filter((t) => t !== flag.type) } },
            });
          }
        }
      }
      return u;
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'flag',
      entityId: id,
      action: 'flag_resolved',
      before: { status: 'open' },
      after: { status: newStatus, action: dto.action },
      reason: dto.note ?? null,
      ip,
    });

    return serializeFlag(updated);
  }

  /** Cancel an open remeasurement request → shipment back to completed (§8). */
  async cancelRemeasure(id: string, user: AuthUser, ip?: string) {
    const request = await this.prisma.remeasureRequest.findFirst({
      where: { id, deletedAt: null },
    });
    if (!request) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Request not found' });
    }
    if (request.status !== 'open') {
      throw new ConflictException({
        code: 'INVALID_TRANSITION',
        message: `Only an open request can be cancelled`,
      });
    }

    const updated = await this.prisma.$transaction(async (tx) => {
      const cancelled = await tx.remeasureRequest.update({
        where: { id },
        data: { status: 'cancelled', closedAt: new Date() },
      });
      await tx.shipment.updateMany({
        where: { id: request.shipmentId, status: 'remeasure_required' },
        data: { status: 'completed' },
      });
      return cancelled;
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'shipment',
      entityId: request.shipmentId,
      action: 'remeasure_cancelled',
      after: { requestId: id, status: 'completed' },
      ip,
    });

    return serializeRemeasure(updated);
  }
}

function serializeFlag(f: Flag) {
  return {
    id: f.id,
    shipmentId: f.shipmentId,
    packageId: f.packageId,
    type: f.type,
    status: f.status,
    resolvedBy: f.resolvedBy,
    note: f.note,
    createdAt: f.createdAt.toISOString(),
  };
}

function serializeRemeasure(r: RemeasureRequest) {
  return {
    id: r.id,
    shipmentId: r.shipmentId,
    packageIds: r.packageIds,
    reason: r.reason,
    note: r.note,
    status: r.status,
    requestedBy: r.requestedBy,
    doneBy: r.doneBy,
    closedAt: r.closedAt?.toISOString() ?? null,
  };
}
