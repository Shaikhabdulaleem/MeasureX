import { BadRequestException, Injectable } from '@nestjs/common';
import { DEFAULT_CHARGEABLE_STEP_KG, DEFAULT_DIVISOR } from '@measurex/shared';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { ConfigUpdateDto } from './dto/config-update.dto';

/**
 * Configuration keys stored in the `config` table (scope = global for M1).
 * Admin CRUD over these arrives in M4; here we only read them, falling back to
 * the defaults below so a fresh database still behaves correctly.
 */
export const CONFIG_KEYS = {
  awbRegex: 'awb_regex',
  volumetricDivisor: 'volumetric_divisor',
  chargeableStepKg: 'chargeable_step_kg',
  actualWeightRequired: 'actual_weight_required',
  mediumConfirmAllowed: 'medium_confirm_allowed',
  minDimensionCm: 'min_dimension_cm',
  maxDimensionCm: 'max_dimension_cm',
  idleAutoCompleteMinutes: 'idle_auto_complete_minutes',
  photoRetentionMonths: 'photo_retention_months',
  localPurgeDays: 'local_purge_days',
} as const;

/** Effective (merged) configuration returned to clients — see OpenAPI EffectiveConfig. */
export interface EffectiveConfig {
  awbRegex: string;
  volumetricDivisor: number;
  dimensionRounding: 'ceil';
  chargeableStepKg: number;
  /** Actual weight required to save (PRD A6). On by default once scale lands (M2). */
  weightRequired: boolean;
  mediumConfirmAllowed: boolean;
  minDimensionCm: number;
  maxDimensionCm: number;
  idleAutoCompleteMinutes: number;
  retention: {
    photoMonths: number;
    localPurgeDays: number;
  };
}

const DEFAULTS: EffectiveConfig = {
  awbRegex: '^AY\\d{11}$',
  volumetricDivisor: DEFAULT_DIVISOR,
  dimensionRounding: 'ceil',
  chargeableStepKg: DEFAULT_CHARGEABLE_STEP_KG,
  weightRequired: true,
  mediumConfirmAllowed: true,
  minDimensionCm: 1,
  maxDimensionCm: 300,
  idleAutoCompleteMinutes: 30,
  retention: { photoMonths: 12, localPurgeDays: 7 },
};

/** Maps an EffectiveConfig-shaped field to its stored config key. */
const FIELD_TO_KEY: Record<string, string> = {
  awbRegex: CONFIG_KEYS.awbRegex,
  volumetricDivisor: CONFIG_KEYS.volumetricDivisor,
  chargeableStepKg: CONFIG_KEYS.chargeableStepKg,
  weightRequired: CONFIG_KEYS.actualWeightRequired,
  mediumConfirmAllowed: CONFIG_KEYS.mediumConfirmAllowed,
  minDimensionCm: CONFIG_KEYS.minDimensionCm,
  maxDimensionCm: CONFIG_KEYS.maxDimensionCm,
  idleAutoCompleteMinutes: CONFIG_KEYS.idleAutoCompleteMinutes,
  photoRetentionMonths: CONFIG_KEYS.photoRetentionMonths,
  localPurgeDays: CONFIG_KEYS.localPurgeDays,
};

@Injectable()
export class ConfigService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /**
   * PUT /config — validate and persist changed global keys (Admin, PRD §11,
   * §14). Only the fields present are changed; each is upserted as a global
   * config row, and the before/after effective config is audited.
   */
  async updateConfig(dto: ConfigUpdateDto, actor: AuthUser, ip?: string): Promise<EffectiveConfig> {
    const before = await this.getEffectiveConfig();

    // Cross-field validation against the merged result (so a partial update that
    // leaves max below an unchanged min is still rejected).
    const merged = { ...before } as EffectiveConfig;
    if (dto.minDimensionCm !== undefined) merged.minDimensionCm = dto.minDimensionCm;
    if (dto.maxDimensionCm !== undefined) merged.maxDimensionCm = dto.maxDimensionCm;
    if (merged.maxDimensionCm < merged.minDimensionCm) {
      throw new BadRequestException({
        code: 'INVALID_CONFIG',
        message: 'maxDimensionCm must be >= minDimensionCm',
      });
    }
    if (dto.awbRegex !== undefined) {
      try {
        new RegExp(dto.awbRegex);
      } catch {
        throw new BadRequestException({
          code: 'INVALID_CONFIG',
          message: 'awbRegex is not a valid regular expression',
        });
      }
    }

    const entries = Object.entries(dto).filter(([, v]) => v !== undefined);
    if (entries.length === 0) return before;

    await this.prisma.$transaction(
      entries.map(([field, value]) => {
        const key = FIELD_TO_KEY[field];
        return this.prisma.config.upsert({
          where: { key },
          update: { value: value as never, updatedBy: actor.sub },
          create: { key, value: value as never, scope: 'global', updatedBy: actor.sub },
        });
      }),
    );

    const after = await this.getEffectiveConfig();
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'config',
      entityId: 'global',
      action: 'config_updated',
      before,
      after,
      ip,
    });
    return after;
  }

  /** Merge global config rows over the built-in defaults. */
  async getEffectiveConfig(): Promise<EffectiveConfig> {
    const rows = await this.prisma.config.findMany({ where: { scope: 'global' } });
    const byKey = new Map(rows.map((r) => [r.key, r.value]));

    const num = (key: string, fallback: number): number => {
      const v = byKey.get(key);
      return typeof v === 'number' ? v : fallback;
    };
    const bool = (key: string, fallback: boolean): boolean => {
      const v = byKey.get(key);
      return typeof v === 'boolean' ? v : fallback;
    };
    const str = (key: string, fallback: string): string => {
      const v = byKey.get(key);
      return typeof v === 'string' ? v : fallback;
    };

    return {
      awbRegex: str(CONFIG_KEYS.awbRegex, DEFAULTS.awbRegex),
      volumetricDivisor: num(CONFIG_KEYS.volumetricDivisor, DEFAULTS.volumetricDivisor),
      dimensionRounding: 'ceil',
      chargeableStepKg: num(CONFIG_KEYS.chargeableStepKg, DEFAULTS.chargeableStepKg),
      weightRequired: bool(CONFIG_KEYS.actualWeightRequired, DEFAULTS.weightRequired),
      mediumConfirmAllowed: bool(CONFIG_KEYS.mediumConfirmAllowed, DEFAULTS.mediumConfirmAllowed),
      minDimensionCm: num(CONFIG_KEYS.minDimensionCm, DEFAULTS.minDimensionCm),
      maxDimensionCm: num(CONFIG_KEYS.maxDimensionCm, DEFAULTS.maxDimensionCm),
      idleAutoCompleteMinutes: num(
        CONFIG_KEYS.idleAutoCompleteMinutes,
        DEFAULTS.idleAutoCompleteMinutes,
      ),
      retention: {
        photoMonths: num(CONFIG_KEYS.photoRetentionMonths, DEFAULTS.retention.photoMonths),
        localPurgeDays: num(CONFIG_KEYS.localPurgeDays, DEFAULTS.retention.localPurgeDays),
      },
    };
  }
}
