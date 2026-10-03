import { Injectable, NotFoundException } from '@nestjs/common';
import { Device, Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { DeviceRegisterDto } from './dto/device.dto';

@Injectable()
export class DevicesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /** GET /devices — Admin inventory (PRD §11). */
  async list(query: { blocked?: string; tier?: string }) {
    const where: Prisma.DeviceWhereInput = { deletedAt: null };
    if (query.blocked === 'true') where.blocked = true;
    if (query.blocked === 'false') where.blocked = false;
    if (query.tier === 'standard' || query.tier === 'ar' || query.tier === 'unsupported') {
      where.tier = query.tier;
    }
    const rows = await this.prisma.device.findMany({
      where,
      orderBy: { lastSeenAt: 'desc' },
    });
    return { items: rows.map(serializeDevice) };
  }

  /** POST /devices/{id}/block — block or unblock a device (Admin, PRD §10, §14). */
  async setBlocked(id: string, blocked: boolean, actor: AuthUser, ip?: string) {
    const before = await this.prisma.device.findFirst({ where: { id, deletedAt: null } });
    if (!before) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Device not found' });
    }
    const device = await this.prisma.device.update({ where: { id }, data: { blocked } });
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'device',
      entityId: id,
      action: blocked ? 'device_blocked' : 'device_unblocked',
      before: { blocked: before.blocked },
      after: { blocked },
      ip,
    });
    return serializeDevice(device);
  }

  /** Upsert a device by install id, recording the current user and tier. */
  async register(dto: DeviceRegisterDto, user: AuthUser) {
    const device = await this.prisma.device.upsert({
      where: { installId: dto.installId },
      update: {
        manufacturer: dto.manufacturer ?? null,
        model: dto.model ?? null,
        os: dto.os ?? null,
        osVersion: dto.osVersion ?? null,
        tier: dto.tier,
        lastUserId: user.sub,
        lastSeenAt: new Date(),
      },
      create: {
        installId: dto.installId,
        manufacturer: dto.manufacturer ?? null,
        model: dto.model ?? null,
        os: dto.os ?? null,
        osVersion: dto.osVersion ?? null,
        tier: dto.tier,
        lastUserId: user.sub,
        lastSeenAt: new Date(),
      },
    });
    return serializeDevice(device);
  }
}

function serializeDevice(d: Device) {
  return {
    id: d.id,
    installId: d.installId,
    manufacturer: d.manufacturer,
    model: d.model,
    os: d.os,
    osVersion: d.osVersion,
    tier: d.tier,
    lastUserId: d.lastUserId,
    lastSeenAt: d.lastSeenAt?.toISOString() ?? null,
    blocked: d.blocked,
  };
}
