import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { ConfigService } from '../config/config.service';
import { assertValidAwb } from '../common/awb';
import { serializeShipmentDetail } from '../common/serializers';
import { nextPackageNumber } from '../common/package-number';

@Injectable()
export class LookupService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
  ) {}

  /**
   * Cross-device history check (PRD §5 step 3, §10). Intentionally NOT branch
   * scoped: it exists to detect an AWB already measured anywhere, so the worker
   * sees previous packages or continues the open shipment's numbering.
   */
  async lookup(rawAwb: string) {
    const cfg = await this.config.getEffectiveConfig();
    const awb = assertValidAwb(rawAwb, cfg.awbRegex);

    const shipment = await this.prisma.shipment.findFirst({
      where: { awb, deletedAt: null },
      include: {
        packages: {
          where: { deletedAt: null },
          orderBy: [{ packageNumber: 'asc' }, { confirmedAt: 'asc' }],
          include: { currentVersion: true, photos: { where: { deletedAt: null } } },
        },
      },
    });

    if (!shipment) {
      return { awb, found: false, shipment: null, nextPackageNumber: 1 };
    }

    return {
      awb,
      found: true,
      shipment: serializeShipmentDetail(shipment),
      nextPackageNumber: nextPackageNumber(shipment.packages),
    };
  }
}
