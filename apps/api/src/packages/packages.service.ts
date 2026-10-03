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
import { RenumberChange, nextPackageNumber, renumberByConfirmedAt } from '../common/package-number';
import { recomputeShipmentTotals } from '../common/totals';
import { canAccessBranch } from '../common/scope';
import { serializePackage, PackageRow } from '../common/serializers';
import { PackageCreateDto } from './dto/package.dto';

const PACKAGE_INCLUDE = {
  currentVersion: true,
  photos: { where: { deletedAt: null } },
} satisfies Prisma.PackageInclude;

/**
 * How the server assigns the package number:
 *  - `append`      : highest existing number + 1, stable once assigned — the
 *                    online single-create path (PRD §7).
 *  - `confirmed_at`: renumber the shipment's active packages by confirmed_at,
 *                    correcting out-of-order offline arrivals — the sync path
 *                    (PRD §10 rule 2).
 */
export type NumberingStrategy = 'append' | 'confirmed_at';

/** How many times to retry an append create that lost the package-number race. */
const MAX_NUMBER_RETRIES = 3;

/** Outcome of a create: the package plus how the caller should report it. */
export interface CreateOutcome {
  package: ReturnType<typeof serializePackage>;
  /** True when this was an idempotent replay (→ HTTP 200 vs 201). */
  replayed: boolean;
  /**
   * True when the package landed on a shipment now measured by two or more
   * devices — kept, but flagged `possible_duplicate` for the Team Leader
   * (PRD §10 rule 3). The sync batch reports these items as `conflict` (§8).
   */
  duplicate: boolean;
}

interface TxResult {
  package: PackageRow;
  replayed: boolean;
  duplicate: boolean;
  renumbered: RenumberChange[];
}

@Injectable()
export class PackagesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly audit: AuditService,
    private readonly scales: ScalesService,
  ) {}

  /**
   * Create a package, idempotently (PRD §7, §10, §13). Used by both the single
   * endpoint (POST /shipments/{awb}/packages) and the sync batch, so one bad
   * item in a batch is just a failed result, not a rolled-back batch.
   */
  async create(
    rawAwb: string,
    dto: PackageCreateDto,
    idempotencyKey: string,
    user: AuthUser,
    ip?: string,
    numbering: NumberingStrategy = 'append',
  ): Promise<CreateOutcome> {
    const cfg = await this.config.getEffectiveConfig();
    const awb = assertValidAwb(rawAwb, cfg.awbRegex);

    this.assertDimensionsInRange(dto, cfg.minDimensionCm, cfg.maxDimensionCm);
    await this.assertWeightRules(dto, cfg.weightRequired, user);

    // Remeasurement completion (PRD §8): this capture supersedes an existing
    // package and reuses its number, rather than appending a new one.
    if (dto.remeasureOfPackageId) {
      return this.remeasure(awb, dto, idempotencyKey, user, cfg, ip);
    }

    const outcome = await this.createWithRetry(awb, dto, idempotencyKey, user, cfg, numbering);

    if (!outcome.replayed) {
      await this.audit.record({
        userId: user.sub,
        role: user.role as never,
        entity: 'package',
        entityId: outcome.package.id,
        action: 'package_created',
        after: serializePackage(outcome.package),
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

      // Renumbering is a change to each moved package, so each is audited
      // (CLAUDE.md rule 3). Only genuine moves are recorded.
      for (const change of outcome.renumbered) {
        if (change.id === outcome.package.id) continue; // its creation already covers v1
        await this.audit.record({
          userId: user.sub,
          role: user.role as never,
          entity: 'package',
          entityId: change.id,
          action: 'package_renumbered',
          before: { packageNumber: change.from },
          after: { packageNumber: change.to },
          reason: 'confirmed_at renumber on sync',
          ip,
          deviceId: dto.deviceId ?? null,
        });
      }

      if (outcome.duplicate) {
        await this.audit.record({
          userId: user.sub,
          role: user.role as never,
          entity: 'package',
          entityId: outcome.package.id,
          action: 'possible_duplicate_flagged',
          after: { awb },
          ip,
          deviceId: dto.deviceId ?? null,
        });
      }
    }

    return {
      package: serializePackage(outcome.package),
      replayed: outcome.replayed,
      duplicate: outcome.duplicate,
    };
  }

  /**
   * Complete a remeasurement (PRD §8). The new capture supersedes an existing
   * active package and REUSES its number; when every package named by the open
   * remeasure request is superseded the shipment returns to `completed`
   * (a System transition). Idempotent on the client UUID / Idempotency-Key.
   */
  private async remeasure(
    awb: string,
    dto: PackageCreateDto,
    idempotencyKey: string,
    user: AuthUser,
    cfg: Awaited<ReturnType<ConfigService['getEffectiveConfig']>>,
    ip?: string,
  ): Promise<CreateOutcome> {
    const oldPackageId = dto.remeasureOfPackageId!;

    const result = await this.prisma.$transaction(
      async (tx) => {
        await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${awb})::bigint)`;

        // Idempotent replay: the new package already landed.
        const existing = await tx.package.findFirst({
          where: { deletedAt: null, OR: [{ id: dto.id }, { idempotencyKey }] },
          include: PACKAGE_INCLUDE,
        });
        if (existing) {
          return { package: existing, replayed: true, completedRequest: null, oldBefore: null };
        }

        const shipment = await tx.shipment.findFirst({ where: { awb, deletedAt: null } });
        if (!shipment) {
          throw new ConflictException({
            code: 'SHIPMENT_NOT_FOUND',
            message: 'Shipment not found for remeasurement',
            details: { awb },
          });
        }
        if (!canAccessBranch(user, shipment.branchId)) {
          throw new ConflictException({
            code: 'SHIPMENT_OTHER_BRANCH',
            message: 'This shipment belongs to another branch',
            details: { awb, branchId: shipment.branchId },
          });
        }
        if (shipment.status !== 'remeasure_required') {
          throw new ConflictException({
            code: 'NO_REMEASURE_PENDING',
            message: `Shipment is ${shipment.status}, not awaiting remeasurement`,
            details: { awb, status: shipment.status },
          });
        }

        const oldPkg = await tx.package.findFirst({
          where: { id: oldPackageId, shipmentId: shipment.id, deletedAt: null },
        });
        if (!oldPkg || oldPkg.status !== 'active') {
          throw new ConflictException({
            code: 'REMEASURE_TARGET_INVALID',
            message: 'The package being remeasured is not an active package on this shipment',
            details: { packageId: oldPackageId },
          });
        }

        // There must be an open request on this shipment that names the package.
        const request = await tx.remeasureRequest.findFirst({
          where: { shipmentId: shipment.id, status: 'open', deletedAt: null },
        });
        if (!request || !request.packageIds.includes(oldPackageId)) {
          throw new ConflictException({
            code: 'REMEASURE_NOT_REQUESTED',
            message: 'No open remeasurement request names this package',
            details: { packageId: oldPackageId },
          });
        }

        // Supersede the old package FIRST so the partial unique index frees its
        // number, then create the new active package reusing that number.
        await tx.package.update({ where: { id: oldPkg.id }, data: { status: 'superseded' } });

        await tx.package.create({
          data: {
            id: dto.id,
            shipmentId: shipment.id,
            packageNumber: oldPkg.packageNumber,
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
            reason: `remeasurement of PKG ${oldPkg.packageNumber ?? '?'}`,
          },
        });
        await tx.package.update({ where: { id: dto.id }, data: { currentVersionId: version.id } });

        // Completion: when no package named by the request is still active, the
        // request is done and the shipment returns to completed (System, §8).
        const stillActive = await tx.package.count({
          where: { id: { in: request.packageIds }, status: 'active', deletedAt: null },
        });
        let completedRequest: string | null = null;
        if (stillActive === 0) {
          await tx.remeasureRequest.update({
            where: { id: request.id },
            data: { status: 'done', doneBy: user.sub, closedAt: new Date() },
          });
          await tx.shipment.update({
            where: { id: shipment.id },
            data: { status: 'completed', completedAt: new Date() },
          });
          completedRequest = request.id;
        }

        await recomputeShipmentTotals(tx, shipment.id);

        const created = await tx.package.findUniqueOrThrow({
          where: { id: dto.id },
          include: PACKAGE_INCLUDE,
        });
        return {
          package: created,
          replayed: false,
          completedRequest,
          oldBefore: { id: oldPkg.id, status: 'active', packageNumber: oldPkg.packageNumber },
        };
      },
      { timeout: 15_000 },
    );

    if (!result.replayed) {
      await this.audit.record({
        userId: user.sub,
        role: user.role as never,
        entity: 'package',
        entityId: oldPackageId,
        action: 'package_remeasured',
        before: result.oldBefore,
        after: { status: 'superseded', replacedBy: result.package.id },
        ip,
        deviceId: dto.deviceId ?? null,
      });
      await this.audit.record({
        userId: user.sub,
        role: user.role as never,
        entity: 'package',
        entityId: result.package.id,
        action: 'package_created',
        after: serializePackage(result.package),
        reason: 'remeasurement',
        ip,
        deviceId: dto.deviceId ?? null,
      });
      if (result.completedRequest) {
        await this.audit.record({
          userId: user.sub,
          role: user.role as never,
          entity: 'shipment',
          entityId: result.package.shipmentId,
          action: 'remeasure_completed',
          after: { status: 'completed', requestId: result.completedRequest },
          ip,
        });
      }
    }

    return {
      package: serializePackage(result.package),
      replayed: result.replayed,
      duplicate: false,
    };
  }

  /**
   * Run the create transaction, retrying on a lost package-number race (only
   * possible with `append`). The per-AWB advisory lock serialises concurrent
   * creates, so the retry is a safety net for an advisory-key hash collision so
   * we never surface a 500.
   */
  private async createWithRetry(
    awb: string,
    dto: PackageCreateDto,
    idempotencyKey: string,
    user: AuthUser,
    cfg: Awaited<ReturnType<ConfigService['getEffectiveConfig']>>,
    numbering: NumberingStrategy,
  ): Promise<TxResult> {
    for (let attempt = 1; ; attempt++) {
      try {
        return await this.runCreateTransaction(awb, dto, idempotencyKey, user, cfg, numbering);
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
    numbering: NumberingStrategy,
  ): Promise<TxResult> {
    return this.prisma.$transaction(
      async (tx) => {
        // Serialise concurrent creates for the same AWB so package numbers are
        // assigned without racing (PRD §7, server is final). The lock releases
        // at transaction end, so the renumber below is never run concurrently
        // for the same shipment.
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
          return { package: existing, replayed: true, duplicate: false, renumbered: [] };
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

        // 5. Assign the number. `append` sets it now (max+1, stable);
        //    `confirmed_at` inserts null and lets the renumber (step 7) assign
        //    it in confirmed_at order.
        let insertNumber: number | null = null;
        if (numbering === 'append') {
          const existingPackages = await tx.package.findMany({
            where: { shipmentId: shipment.id, deletedAt: null },
            select: { packageNumber: true },
          });
          insertNumber = nextPackageNumber(existingPackages);
        }

        await tx.package.create({
          data: {
            id: dto.id,
            shipmentId: shipment.id,
            packageNumber: insertNumber,
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

        // 6. Flags that this package may raise.
        const flagsToAdd: string[] = [];

        // Manual weight (TL/Admin, validated above) → `manual_weight` flag so it
        // surfaces on the dashboard and TL queue (PRD §9, §11).
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
          flagsToAdd.push('manual_weight');
        }

        // 7. Sync path only: renumber in confirmed_at order (PRD §10 rule 2) so
        //    an earlier offline package that syncs late takes its rightful spot.
        const renumbered =
          numbering === 'confirmed_at' ? await renumberByConfirmedAt(tx, shipment.id) : [];

        // 8. Possible duplicate (sync path only, PRD §10 rule 3): another
        //    device already has a package on this shipment that was RECEIVED by
        //    the server after this item was confirmed — i.e. the two were
        //    measured concurrently while this device was offline. Online adds
        //    from two phones (append path, or received before this was
        //    confirmed) never flag. Both packages are kept; flag once for the TL.
        const duplicate =
          numbering === 'confirmed_at' &&
          dto.deviceId != null &&
          (await this.isOfflineDuplicate(
            tx,
            shipment.id,
            dto.id,
            dto.deviceId,
            new Date(dto.confirmedAt),
          ));
        if (duplicate && !shipment.flags.includes('possible_duplicate')) {
          const alreadyOpen = await tx.flag.findFirst({
            where: { shipmentId: shipment.id, type: 'possible_duplicate', status: 'open' },
            select: { id: true },
          });
          if (!alreadyOpen) {
            await tx.flag.create({
              data: { shipmentId: shipment.id, type: 'possible_duplicate', status: 'open' },
            });
          }
          flagsToAdd.push('possible_duplicate');
        }

        if (flagsToAdd.length > 0) {
          const next = Array.from(new Set([...shipment.flags, ...flagsToAdd]));
          await tx.shipment.update({
            where: { id: shipment.id },
            data: { flags: { set: next as never } },
          });
        }

        await recomputeShipmentTotals(tx, shipment.id);

        const created = await tx.package.findUniqueOrThrow({
          where: { id: dto.id },
          include: PACKAGE_INCLUDE,
        });
        return { package: created, replayed: false, duplicate, renumbered };
      },
      { timeout: 15_000 },
    );
  }

  // --- internals -----------------------------------------------------------

  /**
   * True when another device already has an active package on this shipment
   * that the server RECEIVED after the incoming item was confirmed — the
   * signature of two phones measuring the same AWB while offline (PRD §10
   * rule 3). A package received before this item was confirmed is a normal
   * sequential add and does not flag.
   */
  private async isOfflineDuplicate(
    tx: Prisma.TransactionClient,
    shipmentId: string,
    packageId: string,
    deviceId: string,
    confirmedAt: Date,
  ): Promise<boolean> {
    const other = await tx.package.findFirst({
      where: {
        shipmentId,
        status: 'active',
        deletedAt: null,
        id: { not: packageId },
        deviceId: { not: deviceId },
        syncReceivedAt: { gt: confirmedAt },
      },
      select: { id: true },
    });
    return other != null;
  }

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
