import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { ConfigService } from '../config/config.service';
import { AuditService } from '../audit/audit.service';
import { ScalesService } from '../scales/scales.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { assertValidAwb } from '../common/awb';
import { computeVersionBilling } from '../common/billing';
import { nextPackageNumber } from '../common/package-number';
import { recomputeShipmentTotals } from '../common/totals';
import { canAccessBranch } from '../common/scope';
import { serializePackage, PackageRow } from '../common/serializers';
import { PackageCreateDto } from './dto/package.dto';

const PACKAGE_INCLUDE = {
  currentVersion: true,
  photos: { where: { deletedAt: null } },
} satisfies Prisma.PackageInclude;

/** How many times to retry a create that lost the package-number race. */
const MAX_NUMBER_RETRIES = 3;

@Injectable()
export class PackagesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly audit: AuditService,
    private readonly scales: ScalesService,
  ) {}

  /**
   * Create a package, idempotently (PRD §7, §10, §13). Returns the serialized
   * package plus whether this was an idempotent replay (→ HTTP 200 vs 201).
   */
  async create(
    rawAwb: string,
    dto: PackageCreateDto,
    idempotencyKey: string,
    user: AuthUser,
    ip?: string,
  ): Promise<{ package: ReturnType<typeof serializePackage>; replayed: boolean }> {
    const cfg = await this.config.getEffectiveConfig();
    const awb = assertValidAwb(rawAwb, cfg.awbRegex);

    this.assertDimensionsInRange(dto, cfg.minDimensionCm, cfg.maxDimensionCm);
    await this.assertWeightRules(dto, cfg.weightRequired, user);

    const outcome = await this.createWithRetry(awb, dto, idempotencyKey, user, cfg);

    if (!outcome.replayed) {
      await this.audit.record({
        userId: user.sub,
        role: user.role as never,
        entity: 'package',
        entityId: outcome.package.id,
        action: 'package_created',
        after: serializePackage(outcome.package as PackageRow),
        ip,
        deviceId: dto.deviceId ?? null,
      });

      if (dto.weightSource === 'manual') {
        await this.audit.record({
          userId: user.sub,
          role: user.role as never,
          entity: 'package',
          entityId: outcome.package.id,
          action: 'manual_weight_entered',
          after: { actualWeightG: dto.actualWeightG ?? null },
          reason: dto.weightReason ?? null,
          ip,
          deviceId: dto.deviceId ?? null,
        });
      }
    }

    return { package: serializePackage(outcome.package as PackageRow), replayed: outcome.replayed };
  }

  /**
   * Run the create transaction, retrying on a lost package-number race. The
   * per-AWB advisory lock serialises concurrent creates so numbering is
   * deterministic; the retry is a safety net if a conflict still slips through
   * (e.g. advisory-key hash collision) so we never surface a 500.
   */
  private async createWithRetry(
    awb: string,
    dto: PackageCreateDto,
    idempotencyKey: string,
    user: AuthUser,
    cfg: Awaited<ReturnType<ConfigService['getEffectiveConfig']>>,
  ): Promise<{ package: PackageRow; replayed: boolean }> {
    for (let attempt = 1; ; attempt++) {
      try {
        return await this.runCreateTransaction(awb, dto, idempotencyKey, user, cfg);
      } catch (err) {
        if (isPackageNumberConflict(err) && attempt < MAX_NUMBER_RETRIES) {
          continue; // another create took our number — recompute and retry
        }
        throw err;
      }
    }
  }

  private runCreateTransaction(
    awb: string,
    dto: PackageCreateDto,
    idempotencyKey: string,
    user: AuthUser,
    cfg: Awaited<ReturnType<ConfigService['getEffectiveConfig']>>,
  ): Promise<{ package: PackageRow; replayed: boolean }> {
    return this.prisma.$transaction(
      async (tx) => {
        // Serialise concurrent creates for the same AWB so package numbers are
        // assigned without racing (PRD §7, server is final). The lock releases
        // at transaction end.
        await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${awb})::bigint)`;

        // 1. Idempotency: a resent create (same client UUID or Idempotency-Key)
        //    returns the original package untouched (PRD §10 rule 1).
        const existing = await tx.package.findFirst({
          where: {
            deletedAt: null,
            OR: [{ id: dto.id }, { idempotencyKey }],
          },
          include: PACKAGE_INCLUDE,
        });
        if (existing) {
          return { package: existing, replayed: true };
        }

        // 2. Find or create the shipment (created on the first package, §5).
        const shipment = await this.findOrCreateShipment(tx, awb, user.homeBranchId);

        // 3. Branch guard: a package may only be added to a shipment in the
        //    user's branch; a scoped TL/Admin may override (PRD §3).
        if (!canAccessBranch(user, shipment.branchId)) {
          throw new ConflictException({
            code: 'SHIPMENT_OTHER_BRANCH',
            message: 'This shipment belongs to another branch',
            details: { awb, branchId: shipment.branchId },
          });
        }

        // 4. State machine: packages may only be added while in_progress (§8).
        if (shipment.status !== 'in_progress') {
          throw new ConflictException({
            code: 'SHIPMENT_NOT_OPEN',
            message: `Cannot add a package to a ${shipment.status} shipment`,
            details: { awb, status: shipment.status },
          });
        }

        // 5. Server assigns the authoritative number (§7).
        const existingPackages = await tx.package.findMany({
          where: { shipmentId: shipment.id, deletedAt: null },
          select: { packageNumber: true },
        });
        const packageNumber = nextPackageNumber(existingPackages);

        // 6. Create the package, then its immutable v1 version, then link it.
        await tx.package.create({
          data: {
            id: dto.id,
            shipmentId: shipment.id,
            packageNumber,
            provisionalNumber: dto.provisionalNumber ?? null,
            status: 'active',
            stationId: dto.stationId ?? null,
            deviceId: dto.deviceId ?? null,
            measuredBy: user.sub,
            idempotencyKey,
            confirmedAt: new Date(dto.confirmedAt),
            syncReceivedAt: new Date(),
          },
        });

        const billing = computeVersionBilling(
          {
            lengthMm: dto.lengthMm,
            widthMm: dto.widthMm,
            heightMm: dto.heightMm,
            actualWeightG: dto.actualWeightG ?? null,
          },
          cfg,
        );

        const version = await tx.measurementVersion.create({
          data: {
            packageId: dto.id,
            versionNo: 1,
            lengthMm: dto.lengthMm,
            widthMm: dto.widthMm,
            heightMm: dto.heightMm,
            actualWeightG: dto.actualWeightG ?? null,
            weightSource: dto.weightSource ?? 'none',
            scaleId: dto.scaleId ?? null,
            method: dto.method ?? 'manual',
            confidence: dto.confidence ?? null,
            confidenceDetail: (dto.confidenceDetail ?? undefined) as Prisma.InputJsonValue,
            divisorUsed: billing.divisorUsed,
            billingLCm: billing.billingLCm,
            billingWCm: billing.billingWCm,
            billingHCm: billing.billingHCm,
            cbm: billing.cbm,
            volumetricG: billing.volumetricG,
            chargeableG: billing.chargeableG,
            createdBy: user.sub,
          },
        });

        await tx.package.update({
          where: { id: dto.id },
          data: { currentVersionId: version.id },
        });

        // Manual weight (TL/Admin, validated above) raises the `manual_weight`
        // flag so it surfaces on the dashboard and TL queue (PRD §9, §11).
        if (dto.weightSource === 'manual') {
          await tx.flag.create({
            data: {
              shipmentId: shipment.id,
              packageId: dto.id,
              type: 'manual_weight',
              status: 'open',
              note: dto.weightReason ?? null,
            },
          });
          if (!shipment.flags.includes('manual_weight')) {
            await tx.shipment.update({
              where: { id: shipment.id },
              data: { flags: { set: [...shipment.flags, 'manual_weight'] } },
            });
          }
        }

        await recomputeShipmentTotals(tx, shipment.id);

        const created = await tx.package.findUniqueOrThrow({
          where: { id: dto.id },
          include: PACKAGE_INCLUDE,
        });
        return { package: created, replayed: false };
      },
      { timeout: 15_000 },
    );
  }

  // --- internals -----------------------------------------------------------

  private async findOrCreateShipment(tx: Prisma.TransactionClient, awb: string, branchId: string) {
    const found = await tx.shipment.findFirst({ where: { awb, deletedAt: null } });
    if (found) return found;
    try {
      return await tx.shipment.create({
        data: { awb, branchId, status: 'in_progress' },
      });
    } catch (err) {
      // Lost a race to create the first package: re-read the winner.
      if (err instanceof Prisma.PrismaClientKnownRequestError && err.code === 'P2002') {
        const again = await tx.shipment.findFirst({ where: { awb, deletedAt: null } });
        if (again) return again;
      }
      throw err;
    }
  }

  private assertDimensionsInRange(dto: PackageCreateDto, minCm: number, maxCm: number): void {
    const minMm = minCm * 10;
    const maxMm = maxCm * 10;
    const dims: Array<[string, number]> = [
      ['lengthMm', dto.lengthMm],
      ['widthMm', dto.widthMm],
      ['heightMm', dto.heightMm],
    ];
    for (const [name, mm] of dims) {
      if (mm < minMm || mm > maxMm) {
        throw new BadRequestException({
          code: 'DIMENSION_OUT_OF_RANGE',
          message: `Dimension ${name} must be between ${minCm} and ${maxCm} cm`,
          details: { field: name, valueMm: mm, minCm, maxCm },
        });
      }
    }
  }

  /**
   * Weight rules (PRD §9):
   *  - `scale`  → an approved `scaleId` and a weight value are required.
   *  - `manual` → Team Leader / Admin only, with a reason (→ `manual_weight`
   *    flag + audit). Labour is rejected.
   *  - when `actual_weight_required` is on, a usable weight must be present.
   */
  private async assertWeightRules(
    dto: PackageCreateDto,
    weightRequired: boolean,
    user: AuthUser,
  ): Promise<void> {
    const source = dto.weightSource ?? 'none';

    if (source === 'scale') {
      if (!dto.scaleId) {
        throw new BadRequestException({
          code: 'SCALE_ID_REQUIRED',
          message: 'A scaleId is required when weightSource is "scale"',
        });
      }
      if (dto.actualWeightG == null) {
        throw new BadRequestException({
          code: 'WEIGHT_REQUIRED',
          message: 'A scale weight requires actualWeightG',
        });
      }
      // Only an approved scale may be used (PRD §9); throws if missing/unapproved.
      await this.scales.getApprovedOrThrow(dto.scaleId);
    }

    if (source === 'manual') {
      if (user.role !== 'team_leader' && user.role !== 'admin') {
        throw new ForbiddenException({
          code: 'MANUAL_WEIGHT_FORBIDDEN',
          message: 'Manual weight entry is restricted to Team Leader and Admin',
        });
      }
      if (!dto.weightReason?.trim()) {
        throw new BadRequestException({
          code: 'WEIGHT_REASON_REQUIRED',
          message: 'A reason is required for manual weight entry',
        });
      }
      if (dto.actualWeightG == null) {
        throw new BadRequestException({
          code: 'WEIGHT_REQUIRED',
          message: 'A manual weight requires actualWeightG',
        });
      }
    }

    if (weightRequired) {
      const hasWeight = dto.actualWeightG != null && source !== 'none';
      if (!hasWeight) {
        throw new BadRequestException({
          code: 'WEIGHT_REQUIRED',
          message: 'Actual weight is required by configuration',
        });
      }
    }
  }
}

/** True when a Prisma error is a unique conflict on (shipment_id, package_number). */
function isPackageNumberConflict(err: unknown): boolean {
  if (!(err instanceof Prisma.PrismaClientKnownRequestError) || err.code !== 'P2002') {
    return false;
  }
  const target = err.meta?.target;
  const fields = Array.isArray(target) ? target.join(',') : String(target ?? '');
  return fields.includes('package_number');
}
