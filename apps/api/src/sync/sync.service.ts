import { HttpException, Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { shipmentScopeWhere } from '../common/scope';
import { PackagesService } from '../packages/packages.service';
import { SyncBatchDto, SyncPackageDto } from './dto/sync.dto';

/** Per-item result mirrored to the mobile sync record states (PRD §8). */
export interface SyncItemResult {
  id: string;
  status: 'synced' | 'conflict' | 'failed';
  packageNumber: number | null;
  error?: { code: string; message: string };
}

@Injectable()
export class SyncService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly packages: PackagesService,
  ) {}

  /**
   * POST /sync/batch — upload up to 50 packages (PRD §10). Each item is created
   * in its own transaction (via PackagesService.create), so partial success is
   * possible: one bad item becomes a `failed` result and the rest still land.
   * Idempotent per item (the client UUID doubles as the idempotency key), so a
   * replayed batch returns the same package numbers and creates no duplicates.
   *
   * Items are processed in `confirmedAt` order; the server renumbers each
   * shipment authoritatively on every insert.
   */
  async batch(dto: SyncBatchDto, user: AuthUser, ip?: string): Promise<SyncItemResult[]> {
    const items = [...dto.packages].sort(
      (a, b) => new Date(a.confirmedAt).getTime() - new Date(b.confirmedAt).getTime(),
    );

    const results: SyncItemResult[] = [];
    for (const item of items) {
      results.push(await this.syncOne(item, user, ip));
    }

    // A later item can renumber an earlier one (confirmed_at order), so the
    // number captured mid-batch may be stale. Re-read the final numbers for
    // every stored item so the device shows the authoritative PKG number.
    const storedIds = results.filter((r) => r.status !== 'failed').map((r) => r.id);
    if (storedIds.length > 0) {
      const finals = await this.prisma.package.findMany({
        where: { id: { in: storedIds } },
        select: { id: true, packageNumber: true },
      });
      const byId = new Map(finals.map((p) => [p.id, p.packageNumber]));
      for (const r of results) {
        if (byId.has(r.id)) r.packageNumber = byId.get(r.id) ?? null;
      }
    }

    return results;
  }

  private async syncOne(
    item: SyncPackageDto,
    user: AuthUser,
    ip?: string,
  ): Promise<SyncItemResult> {
    try {
      // The client UUID is the idempotency key for a synced package: resending
      // never duplicates (PRD §10 rule 1).
      const outcome = await this.packages.create(item.awb, item, item.id, user, ip, 'confirmed_at');
      return {
        id: item.id,
        // A duplicate was still stored on the server; the device records it as
        // `conflict` and it is routed to the Team Leader (PRD §8, §10 rule 3).
        status: outcome.duplicate ? 'conflict' : 'synced',
        packageNumber: outcome.package.packageNumber ?? null,
      };
    } catch (err) {
      return { id: item.id, status: 'failed', packageNumber: null, error: toError(err) };
    }
  }

  /**
   * GET /sync/status — the server's view of a device's recent packages. The
   * device is authoritative for `pending`/`failed` (work not yet accepted), so
   * those are reported as 0 here; the server only knows what it stored. We
   * report the `conflict` count (this device's active packages on shipments
   * flagged `possible_duplicate`) and echo recent `synced` items. Scoped to the
   * caller's branch/role.
   */
  async status(deviceId: string | undefined, user: AuthUser) {
    const where = {
      deletedAt: null,
      status: 'active' as const,
      ...(deviceId ? { deviceId } : {}),
      shipment: { is: shipmentScopeWhere(user) },
    };

    const recent = await this.prisma.package.findMany({
      where,
      orderBy: { syncReceivedAt: 'desc' },
      take: 100,
      select: {
        id: true,
        packageNumber: true,
        shipment: { select: { flags: true } },
      },
    });

    const items: SyncItemResult[] = recent.map((p) => {
      const conflict = p.shipment.flags.includes('possible_duplicate');
      return {
        id: p.id,
        status: conflict ? 'conflict' : 'synced',
        packageNumber: p.packageNumber,
      };
    });

    return {
      pending: 0,
      failed: 0,
      conflict: items.filter((i) => i.status === 'conflict').length,
      items,
    };
  }
}

/** Normalise a thrown error into the `{code,message}` the client expects. */
function toError(err: unknown): { code: string; message: string } {
  if (err instanceof HttpException) {
    const body = err.getResponse();
    if (body && typeof body === 'object') {
      const b = body as Record<string, unknown>;
      return {
        code: typeof b.code === 'string' ? b.code : 'ERROR',
        message: typeof b.message === 'string' ? b.message : err.message,
      };
    }
    return { code: 'ERROR', message: err.message };
  }
  return { code: 'ERROR', message: 'Internal error' };
}
