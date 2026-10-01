import { Prisma } from '@prisma/client';
import { computeBilling } from '@measurex/shared';
import { EffectiveConfig } from '../config/config.service';

export interface MeasurementDims {
  lengthMm: number;
  widthMm: number;
  heightMm: number;
  actualWeightG?: number | null;
}

/**
 * The server-authoritative billing fields for a `measurement_version`, computed
 * from integer base units with the single shared formula set (CLAUDE.md rule 2).
 * Mobile previews the same numbers via the Dart port; the server value is final.
 */
export function computeVersionBilling(
  dims: MeasurementDims,
  config: EffectiveConfig,
): {
  divisorUsed: number;
  billingLCm: number;
  billingWCm: number;
  billingHCm: number;
  cbm: Prisma.Decimal;
  volumetricG: number;
  chargeableG: number;
} {
  const result = computeBilling({
    lengthMm: dims.lengthMm,
    widthMm: dims.widthMm,
    heightMm: dims.heightMm,
    actualWeightG: dims.actualWeightG ?? null,
    divisor: config.volumetricDivisor,
    chargeableStepKg: config.chargeableStepKg,
  });

  return {
    divisorUsed: result.divisorUsed,
    billingLCm: result.billingLCm,
    billingWCm: result.billingWCm,
    billingHCm: result.billingHCm,
    cbm: new Prisma.Decimal(result.cbm.toFixed(4)),
    volumetricG: result.volumetricG,
    chargeableG: result.chargeableG,
  };
}
