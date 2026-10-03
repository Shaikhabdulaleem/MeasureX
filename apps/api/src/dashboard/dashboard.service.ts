import { Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { shipmentScopeWhere } from '../common/scope';

interface Window {
  from: Date;
  to: Date;
}

/** KPIs for a time window, computed from packages/versions/events (PRD §11, §15). */
export interface Kpis {
  from: string;
  to: string;
  shipments: number;
  packages: number;
  cbm: number;
  chargeableG: number;
  manualEntryRate: number; // 0..1 over active packages in the window
  retakeRate: number; // retake events / measure_start events
  flagsOpen: number;
  remeasuresOpen: number;
}

function startOfUtcDay(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
}

@Injectable()
export class DashboardService {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * GET /dashboard/kpis — returns a `today` block and a `range` block (the range
   * defaults to the last 7 days). Everything is branch-scoped to the caller.
   */
  async kpis(user: AuthUser, dateFrom?: string, dateTo?: string) {
    const now = new Date();
    const today: Window = { from: startOfUtcDay(now), to: now };
    const range: Window = {
      from: dateFrom ? new Date(dateFrom) : new Date(now.getTime() - 7 * 86_400_000),
      to: dateTo ? new Date(dateTo) : now,
    };
    const scope = shipmentScopeWhere(user);
    const [todayKpis, rangeKpis] = await Promise.all([
      this.windowKpis(scope, today),
      this.windowKpis(scope, range),
    ]);
    return { today: todayKpis, range: rangeKpis };
  }

  private async windowKpis(scope: Prisma.ShipmentWhereInput, w: Window): Promise<Kpis> {
    // Active packages in scope whose shipment was created in the window.
    const pkgWhere: Prisma.PackageWhereInput = {
      deletedAt: null,
      status: 'active',
      shipment: { is: { AND: [scope, { deletedAt: null }] } },
      confirmedAt: { gte: w.from, lte: w.to },
    };

    const packages = await this.prisma.package.findMany({
      where: pkgWhere,
      select: {
        shipmentId: true,
        currentVersion: { select: { method: true, cbm: true, chargeableG: true } },
      },
    });

    const shipmentIds = new Set<string>();
    let manual = 0;
    let cbm = new Prisma.Decimal(0);
    let chargeableG = 0;
    for (const p of packages) {
      shipmentIds.add(p.shipmentId);
      if (p.currentVersion) {
        if (p.currentVersion.method === 'manual') manual += 1;
        cbm = cbm.add(p.currentVersion.cbm);
        chargeableG += p.currentVersion.chargeableG;
      }
    }

    const [flagsOpen, remeasuresOpen, measureStarts, retakes] = await Promise.all([
      this.prisma.flag.count({
        where: { status: 'open', deletedAt: null, shipment: { is: scope } },
      }),
      this.prisma.remeasureRequest.count({
        where: { status: 'open', deletedAt: null, shipment: { is: scope } },
      }),
      this.prisma.measurementEvent.count({
        where: { type: 'measure_start', occurredAt: { gte: w.from, lte: w.to } },
      }),
      this.prisma.measurementEvent.count({
        where: { type: 'retake', occurredAt: { gte: w.from, lte: w.to } },
      }),
    ]);

    return {
      from: w.from.toISOString(),
      to: w.to.toISOString(),
      shipments: shipmentIds.size,
      packages: packages.length,
      cbm: Number(cbm.toFixed(4)),
      chargeableG,
      manualEntryRate: packages.length ? manual / packages.length : 0,
      retakeRate: measureStarts ? retakes / measureStarts : 0,
      flagsOpen,
      remeasuresOpen,
    };
  }
}
