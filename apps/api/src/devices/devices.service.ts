import { Injectable } from '@nestjs/common';
import { Device } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { DeviceRegisterDto } from './dto/device.dto';

@Injectable()
export class DevicesService {
  constructor(private readonly prisma: PrismaService) {}

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
