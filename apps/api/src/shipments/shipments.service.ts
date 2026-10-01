import { ConflictException, Injectable, NotFoundException } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { assertValidAwb, normaliseAwb } from '../common/awb';
import { shipmentScopeWhere } from '../common/scope';
import { serializeShipment, serializeShipmentDetail } from '../common/serializers';
import { ShipmentQueryDto } from './dto/shipment-query.dto';

const DETAIL_INCLUDE = {
  packages: {
    where: { deletedAt: null },
    orderBy: [{ packageNumber: 'asc' as const }, { confirmedAt: 'asc' as const }],
    include: { currentVersion: true, photos: { where: { deletedAt: null } } },
  },
} satisfies Prisma.ShipmentInclude;

const DEFAULT_LIMIT = 50;

@Injectable()
export class ShipmentsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /** GET /shipments — scoped, filtered, cursor-paginated. */
  async list(user: AuthUser, query: ShipmentQueryDto) {
    const limit = query.limit ?? DEFAULT_LIMIT;
    const where = this.buildWhere(user, query);

    const rows = await this.prisma.shipment.findMany({
      where,
      orderBy: [{ createdAt: 'desc' }, { id: 'desc' }],
      take: limit + 1,
      ...(query.cursor ? { cursor: { id: query.cursor }, skip: 1 } : {}),
    });

    const hasMore = rows.length > limit;
    const page = hasMore ? rows.slice(0, limit) : rows;
    return {
      items: page.map(serializeShipment),
      nextCursor: hasMore ? page[page.length - 1]!.id : null,
    };
  }

  /** GET /shipments/{awb} — detail with packages, within the caller's scope. */
  async detail(rawAwb: string, user: AuthUser) {
    const awb = normaliseAwb(rawAwb);
    const shipment = await this.prisma.shipment.findFirst({
      where: { AND: [{ awb, deletedAt: null }, shipmentScopeWhere(user)] },
      include: DETAIL_INCLUDE,
    });
    if (!shipment) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Shipment not found' });
    }
    return serializeShipmentDetail(shipment);
  }

  /** POST /shipments/{awb}/complete — in_progress → completed (§8). */
  async complete(rawAwb: string, user: AuthUser, ip?: string) {
    const awb = normaliseAwb(rawAwb);
    const shipment = await this.prisma.shipment.findFirst({
      where: { AND: [{ awb, deletedAt: null }, shipmentScopeWhere(user)] },
    });
    if (!shipment) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Shipment not found' });
    }
    if (shipment.status !== 'in_progress') {
      throw new ConflictException({
        code: 'INVALID_TRANSITION',
        message: `Cannot complete a ${shipment.status} shipment`,
        details: { from: shipment.status, to: 'completed' },
      });
    }

    const updated = await this.prisma.shipment.update({
      where: { id: shipment.id },
      data: { status: 'completed', completedAt: new Date() },
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'shipment',
      entityId: shipment.id,
      action: 'shipment_completed',
      before: { status: shipment.status },
      after: { status: updated.status, completedAt: updated.completedAt },
      ip,
    });

    return serializeShipment(updated);
  }

  // --- internals -----------------------------------------------------------

  private buildWhere(user: AuthUser, query: ShipmentQueryDto): Prisma.ShipmentWhereInput {
    const and: Prisma.ShipmentWhereInput[] = [{ deletedAt: null }, shipmentScopeWhere(user)];

    if (query.branchId) and.push({ branchId: query.branchId });
    if (query.status) and.push({ status: query.status });
    if (query.flag) and.push({ flags: { has: query.flag } });
    if (query.awb) {
      and.push({ awb: { contains: query.awb.toUpperCase() } });
    }
    if (query.dateFrom || query.dateTo) {
      and.push({
        createdAt: {
          ...(query.dateFrom ? { gte: new Date(query.dateFrom) } : {}),
          ...(query.dateTo ? { lte: new Date(query.dateTo) } : {}),
        },
      });
    }

    // Per-package filters collapse into a single `packages.some(...)` so a
    // shipment matches only when one package satisfies all of them.
    const pkgWhere: Prisma.PackageWhereInput = { deletedAt: null };
    let pkgFiltered = false;
    if (query.employeeId) {
      pkgWhere.measuredBy = query.employeeId;
      pkgFiltered = true;
    }
    const versionWhere: Prisma.MeasurementVersionWhereInput = {};
    if (query.confidence) versionWhere.confidence = query.confidence;
    if (query.method) versionWhere.method = query.method;
    if (Object.keys(versionWhere).length > 0) {
      pkgWhere.currentVersion = versionWhere;
      pkgFiltered = true;
    }
    if (pkgFiltered) {
      and.push({ packages: { some: pkgWhere } });
    }

    return { AND: and };
  }

  /** Reusable AWB validation for controllers that need it up front. */
  validateAwb(rawAwb: string, regex: string): string {
    return assertValidAwb(rawAwb, regex);
  }
}
