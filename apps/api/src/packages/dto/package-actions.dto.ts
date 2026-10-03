import {
  IsEnum,
  IsInt,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Min,
  MinLength,
} from 'class-validator';
import { Confidence, MeasurementMethod, WeightSource } from '@prisma/client';

/**
 * Correct a package (PRD §8, §11). Team Leader / Admin only; a reason is
 * mandatory. This creates a NEW immutable measurement_version — the old version
 * is never edited or deleted (CLAUDE.md rule 3). Base units only (mm, g); the
 * server recomputes every billing figure (CLAUDE.md rule 2).
 *
 * Weight carry-over: when no weight is supplied the previous version's weight,
 * source and scale are carried into the new version, so a dimensions-only
 * correction keeps the measured weight (PRD §7). Supply `actualWeightG` +
 * `weightSource` to change it; a `manual` weight requires `weightReason`.
 */
export class PackageCorrectionDto {
  @IsInt()
  @Min(1)
  lengthMm!: number;

  @IsInt()
  @Min(1)
  widthMm!: number;

  @IsInt()
  @Min(1)
  heightMm!: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  actualWeightG?: number | null;

  @IsOptional()
  @IsEnum(WeightSource)
  weightSource?: WeightSource;

  @IsOptional()
  @IsUUID()
  scaleId?: string;

  /** Required when `weightSource = manual` (PRD §9). */
  @IsOptional()
  @IsString()
  @MinLength(1)
  weightReason?: string;

  @IsOptional()
  @IsEnum(MeasurementMethod)
  method?: MeasurementMethod;

  @IsOptional()
  @IsEnum(Confidence)
  confidence?: Confidence;

  @IsOptional()
  @IsObject()
  confidenceDetail?: Record<string, unknown>;

  /** Mandatory reason for the correction — stored on the version and audited. */
  @IsString()
  @MinLength(1)
  reason!: string;
}

/** Void a package (PRD §8). Team Leader / Admin only; a reason is mandatory. */
export class PackageVoidDto {
  @IsString()
  @MinLength(1)
  reason!: string;
}
