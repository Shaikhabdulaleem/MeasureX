import { BadRequestException, ConflictException, Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { ConfigService } from '../config/config.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { assertValidAwb } from '../common/awb';
import { computeVersionBilling } from '../common/billing';
import { nextPackageNumber } from '../common/package-number';
import { recomputeShipmentTotals } from '../common/totals';
import { serializePackage, PackageRow } from '../common/serializers';
import { PackageCreateDto } from './dto/package.dto';

const PACKAGE_INCLUDE = {
  currentVersion: true,
  photos: { where: { deletedAt: null } },
} satisfies Prisma.PackageInclude;

@Injectable()
export class PackagesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly audit: AuditService,
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
    this.assertWeight(dto, cfg.weightRequired);

    const outcome = await this.prisma.$transaction(async (tx) => {
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

      // 3. State machine: packages may only be added while in_progress (§8).
      if (shipment.status !== 'in_progress') {
        throw new ConflictException({
          code: 'SHIPMENT_NOT_OPEN',
          message: `Cannot add a package to a ${shipment.status} shipment`,
          details: { awb, status: shipment.status },
        });
      }

      // 4. Server assigns the authoritative number (§7).
      const existingPackages = await tx.package.findMany({
        where: { shipmentId: shipment.id, deletedAt: null },
        select: { packageNumber: true },
      });
      const packageNumber = nextPackageNumber(existingPackages);

      // 5. Create the package, then its immutable v1 version, then link it.
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

      await recomputeShipmentTotals(tx, shipment.id);

      const created = await tx.package.findUniqueOrThrow({
        where: { id: dto.id },
        include: PACKAGE_INCLUDE,
      });
      return { package: created, replayed: false };
    });

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
    }

    return { package: serializePackage(outcome.package as PackageRow), replayed: outcome.replayed };
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

  private assertWeight(dto: PackageCreateDto, weightRequired: boolean): void {
    if (!weightRequired) return;
    const hasWeight = dto.actualWeightG != null && (dto.weightSource ?? 'none') !== 'none';
    if (!hasWeight) {
      throw new BadRequestException({
        code: 'WEIGHT_REQUIRED',
        message: 'Actual weight is required by configuration',
      });
    }
  }
}
