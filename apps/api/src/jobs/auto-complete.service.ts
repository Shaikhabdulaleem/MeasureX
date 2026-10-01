import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { ConfigService } from '../config/config.service';
import { AuditService } from '../audit/audit.service';

/**
 * Auto-completes shipments left open and idle (PRD §5 step 10, §7, §8). "Idle"
 * = no activity for the configured number of minutes (default 30); shipment
 * `updatedAt` tracks the last package added. Pure and directly callable so it
 * can be tested without a scheduler/Redis; the BullMQ scheduler just calls it.
 */
@Injectable()
export class AutoCompleteService {
  private readonly logger = new Logger(AutoCompleteService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly audit: AuditService,
  ) {}

  async completeIdleShipments(now: Date = new Date()): Promise<number> {
    const cfg = await this.config.getEffectiveConfig();
    const cutoff = new Date(now.getTime() - cfg.idleAutoCompleteMinutes * 60_000);

    const stale = await this.prisma.shipment.findMany({
      where: { status: 'in_progress', deletedAt: null, updatedAt: { lt: cutoff } },
      select: { id: true },
    });
    if (stale.length === 0) return 0;

    for (const { id } of stale) {
      await this.prisma.shipment.update({
        where: { id },
        data: { status: 'completed', completedAt: now },
      });
      await this.audit.record({
        userId: null,
        role: null,
        entity: 'shipment',
        entityId: id,
        action: 'shipment_auto_completed',
        reason: `idle > ${cfg.idleAutoCompleteMinutes} min`,
        after: { status: 'completed' },
      });
    }

    this.logger.log(`Auto-completed ${stale.length} idle shipment(s)`);
    return stale.length;
  }
}
