import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { Prisma, Scale } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { ScaleCreateDto, ScaleUpdateDto } from './dto/scale.dto';

@Injectable()
export class ScalesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /**
   * List scales (PRD §9 approved-model list). `approvedOnly` is the default for
   * selection surfaces (mobile only ever binds an approved scale); Admin UIs
   * pass false to see the full list.
   */
  async list(approvedOnly = false): Promise<ReturnType<typeof serializeScale>[]> {
    const scales = await this.prisma.scale.findMany({
      where: { deletedAt: null, ...(approvedOnly ? { approved: true } : {}) },
      orderBy: { model: 'asc' },
    });
    return scales.map(serializeScale);
  }

  async get(id: string): Promise<ReturnType<typeof serializeScale>> {
    return serializeScale(await this.findOrThrow(id));
  }

  /** Fetch an approved scale or throw — used when a package names a scaleId (PRD §9). */
  async getApprovedOrThrow(id: string): Promise<Scale> {
    const scale = await this.findOrThrow(id);
    if (!scale.approved) {
      throw new BadRequestException({
        code: 'SCALE_NOT_APPROVED',
        message: 'Only an approved scale may be used',
        details: { scaleId: id },
      });
    }
    return scale;
  }

  async create(dto: ScaleCreateDto, user: AuthUser, ip?: string) {
    const scale = await this.prisma.scale.create({
      data: {
        model: dto.model,
        connection: dto.connection,
        adapterKey: dto.adapterKey,
        approved: dto.approved ?? false,
        ...thresholdData(dto),
      },
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'scale',
      entityId: scale.id,
      action: 'scale_created',
      after: serializeScale(scale),
      ip,
    });

    return serializeScale(scale);
  }

  async update(id: string, dto: ScaleUpdateDto, user: AuthUser, ip?: string) {
    const before = await this.findOrThrow(id);
    const scale = await this.prisma.scale.update({
      where: { id },
      data: {
        ...(dto.model !== undefined ? { model: dto.model } : {}),
        ...(dto.connection !== undefined ? { connection: dto.connection } : {}),
        ...(dto.adapterKey !== undefined ? { adapterKey: dto.adapterKey } : {}),
        ...(dto.approved !== undefined ? { approved: dto.approved } : {}),
        ...thresholdData(dto),
      },
    });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'scale',
      entityId: scale.id,
      action: 'scale_updated',
      before: serializeScale(before),
      after: serializeScale(scale),
      ip,
    });

    return serializeScale(scale);
  }

  private async findOrThrow(id: string): Promise<Scale> {
    const scale = await this.prisma.scale.findFirst({ where: { id, deletedAt: null } });
    if (!scale) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Scale not found' });
    }
    return scale;
  }
}

type ThresholdData = Partial<
  Pick<
    Prisma.ScaleUncheckedCreateInput,
    'stabilityWindow' | 'stabilityToleranceG' | 'stabilityWindowMs' | 'minWeightG' | 'staleAfterMs'
  >
>;

/** Only copy threshold fields that were actually provided. */
function thresholdData(dto: ScaleCreateDto | ScaleUpdateDto): ThresholdData {
  const data: ThresholdData = {};
  if (dto.stabilityWindow !== undefined) data.stabilityWindow = dto.stabilityWindow;
  if (dto.stabilityToleranceG !== undefined) data.stabilityToleranceG = dto.stabilityToleranceG;
  if (dto.stabilityWindowMs !== undefined) data.stabilityWindowMs = dto.stabilityWindowMs;
  if (dto.minWeightG !== undefined) data.minWeightG = dto.minWeightG;
  if (dto.staleAfterMs !== undefined) data.staleAfterMs = dto.staleAfterMs;
  return data;
}

export function serializeScale(s: Scale) {
  return {
    id: s.id,
    model: s.model,
    connection: s.connection,
    adapterKey: s.adapterKey,
    approved: s.approved,
    stabilityWindow: s.stabilityWindow,
    stabilityToleranceG: s.stabilityToleranceG,
    stabilityWindowMs: s.stabilityWindowMs,
    minWeightG: s.minWeightG,
    staleAfterMs: s.staleAfterMs,
  };
}
