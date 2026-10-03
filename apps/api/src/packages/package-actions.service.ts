import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { ConfigService } from '../config/config.service';
import { AuditService } from '../audit/audit.service';
import { ScalesService } from '../scales/scales.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { computeVersionBilling } from '../common/billing';
import { recomputeShipmentTotals } from '../common/totals';
import { canAccessBranch } from '../common/scope';
import { serializePackage, serializeVersion } from '../common/serializers';
import { PackageCorrectionDto, PackageVoidDto } from './dto/package-actions.dto';

const PACKAGE_INCLUDE = {
  currentVersion: true,
  photos: { where: { deletedAt: null } },
} satisfies Prisma.PackageInclude;

/**
 * Team-Leader / Admin mutations on an existing package: correct and void
 * (PRD §8, §11). Both are branch-scoped, audited with before/after + reason,
 * and recompute the shipment totals. A correction never edits a version — it
 * appends a new one and repoints `currentVersionId` (CLAUDE.md rule 3). The
 * same API backs the web and the mobile Team-Leader tools (PRD §11).
 */
@Injectable()
export class PackageActionsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly audit: AuditService,
    private readonly scales: ScalesService,
  ) {}

  /** POST /packages/{id}/corrections — append a new version (reason required). */
  async correct(packageId: string, dto: PackageCorrectionDto, user: AuthUser, ip?: string) {
    const cfg = await this.config.getEffectiveConfig();
    this.assertDimensionsInRange(dto, cfg.minDimensionCm, cfg.maxDimensionCm);

    const pkg = await this.loadActivePackage(packageId, user);
    const prev = pkg.currentVersion;

    // Weight: use the supplied value, else carry over the previous version's
    // weight/source/scale so a dimensions-only correction keeps the weight.
    const weightProvided = dto.weightSource !== undefined || dto.actualWeightG !== undefined;
    const weightSource = weightProvided
      ? (dto.weightSource ?? 'none')
      : (prev?.weightSource ?? 'none');
    const actualWeightG = weightProvided
      ? (dto.actualWeightG ?? null)
      : (prev?.actualWeightG ?? null);
    const scaleId = weightProvided ? (dto.scaleId ?? null) : (prev?.scaleId ?? null);

    await this.assertWeightRules(weightSource, actualWeightG, scaleId, dto.weightReason, user);

    const billing = computeVersionBilling(
      { lengthMm: dto.lengthMm, widthMm: dto.widthMm, heightMm: dto.heightMm, actualWeightG },
      cfg,
    );

    const result = await this.prisma.$transaction(async (tx) => {
      const maxVersion = await tx.measurementVersion.aggregate({
        where: { packageId },
        _max: { versionNo: true },
      });
      const versionNo = (maxVersion._max.versionNo ?? 0) + 1;

      const version = await tx.measurementVersion.create({
        data: {
          packageId,
          versionNo,
          lengthMm: dto.lengthMm,
          widthMm: dto.widthMm,
          heightMm: dto.heightMm,
          actualWeightG,
          weightSource,
          scaleId,
          method: dto.method ?? prev?.method ?? 'manual',
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
          reason: dto.reason,
        },
      });

      await tx.package.update({
        where: { id: packageId },
        data: { currentVersionId: version.id },
      });

      // A corrected manual weight is flagged like a captured one (PRD §9, §11).
      if (weightSource === 'manual') {
        await tx.flag.create({
          data: {
            shipmentId: pkg.shipmentId,
            packageId,
            type: 'manual_weight',
            status: 'open',
            note: dto.weightReason ?? dto.reason,
          },
        });
        await this.addShipmentFlag(tx, pkg.shipmentId, 'manual_weight');
      }

      await recomputeShipmentTotals(tx, pkg.shipmentId);

      return tx.package.findUniqueOrThrow({ where: { id: packageId }, include: PACKAGE_INCLUDE });
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'package',
      entityId: packageId,
      action: 'package_corrected',
      before: prev ? serializeVersion(prev) : null,
      after: result.currentVersion ? serializeVersion(result.currentVersion) : null,
      reason: dto.reason,
      ip,
    });

    return serializePackage(result);
  }

  /** POST /packages/{id}/void — exclude from totals, keep the number (reason required). */
  async void(packageId: string, dto: PackageVoidDto, user: AuthUser, ip?: string) {
    const pkg = await this.loadActivePackage(packageId, user);

    const result = await this.prisma.$transaction(async (tx) => {
      await tx.package.update({ where: { id: packageId }, data: { status: 'void' } });
      await recomputeShipmentTotals(tx, pkg.shipmentId);
      return tx.package.findUniqueOrThrow({ where: { id: packageId }, include: PACKAGE_INCLUDE });
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'package',
      entityId: packageId,
      action: 'package_voided',
      before: { status: pkg.status, packageNumber: pkg.packageNumber },
      after: { status: 'void', packageNumber: pkg.packageNumber },
      reason: dto.reason,
      ip,
    });

    return serializePackage(result);
  }

  // --- internals -----------------------------------------------------------

  /**
   * Load a package that may be acted on: non-deleted, `active`, and within the
   * caller's branch scope. Throws 404 when missing/out-of-scope, 409 when not
   * active (void/superseded cannot be corrected or re-voided).
   */
  private async loadActivePackage(packageId: string, user: AuthUser) {
    const pkg = await this.prisma.package.findFirst({
      where: { id: packageId, deletedAt: null },
      include: { ...PACKAGE_INCLUDE, shipment: { select: { branchId: true } } },
    });
    if (!pkg || !canAccessBranch(user, pkg.shipment.branchId)) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Package not found' });
    }
    if (pkg.status !== 'active') {
      throw new ConflictException({
        code: 'PACKAGE_NOT_ACTIVE',
        message: `Cannot act on a ${pkg.status} package`,
        details: { status: pkg.status },
      });
    }
    return pkg;
  }

  private async addShipmentFlag(tx: Prisma.TransactionClient, shipmentId: string, type: string) {
    const shipment = await tx.shipment.findUniqueOrThrow({
      where: { id: shipmentId },
      select: { flags: true },
    });
    if (!shipment.flags.includes(type as never)) {
      await tx.shipment.update({
        where: { id: shipmentId },
        data: { flags: { set: [...shipment.flags, type as never] } },
      });
    }
  }

  private assertDimensionsInRange(dto: PackageCorrectionDto, minCm: number, maxCm: number): void {
    const minMm = minCm * 10;
    const maxMm = maxCm * 10;
    for (const [name, mm] of [
      ['lengthMm', dto.lengthMm],
      ['widthMm', dto.widthMm],
      ['heightMm', dto.heightMm],
    ] as const) {
      if (mm < minMm || mm > maxMm) {
        throw new BadRequestException({
          code: 'DIMENSION_OUT_OF_RANGE',
          message: `Dimension ${name} must be between ${minCm} and ${maxCm} cm`,
          details: { field: name, valueMm: mm, minCm, maxCm },
        });
      }
    }
  }

  /** Weight validity for a correction (mirrors the create path, PRD §9). */
  private async assertWeightRules(
    source: string,
    actualWeightG: number | null,
    scaleId: string | null,
    weightReason: string | undefined,
    user: AuthUser,
  ): Promise<void> {
    if (source === 'scale') {
      if (!scaleId) {
        throw new BadRequestException({
          code: 'SCALE_ID_REQUIRED',
          message: 'A scaleId is required when weightSource is "scale"',
        });
      }
      if (actualWeightG == null) {
        throw new BadRequestException({
          code: 'WEIGHT_REQUIRED',
          message: 'A scale weight requires actualWeightG',
        });
      }
      await this.scales.getApprovedOrThrow(scaleId);
    }

    if (source === 'manual') {
      if (user.role !== 'team_leader' && user.role !== 'admin') {
        throw new ForbiddenException({
          code: 'MANUAL_WEIGHT_FORBIDDEN',
          message: 'Manual weight entry is restricted to Team Leader and Admin',
        });
      }
      if (!weightReason?.trim()) {
        throw new BadRequestException({
          code: 'WEIGHT_REASON_REQUIRED',
          message: 'A reason is required for manual weight entry',
        });
      }
      if (actualWeightG == null) {
        throw new BadRequestException({
          code: 'WEIGHT_REQUIRED',
          message: 'A manual weight requires actualWeightG',
        });
      }
    }
  }
}
