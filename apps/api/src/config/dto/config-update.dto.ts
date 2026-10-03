import { IsBoolean, IsInt, IsNumber, IsOptional, IsString, Min } from 'class-validator';

/**
 * Update global configuration (Admin, PRD §11, §14). Every field is optional;
 * only the keys present are changed. Values are validated in the service
 * (e.g. the AWB regex must compile, max >= min) before being persisted, and the
 * change is audited with before/after.
 */
export class ConfigUpdateDto {
  @IsOptional()
  @IsString()
  awbRegex?: string;

  @IsOptional()
  @IsInt()
  @Min(1)
  volumetricDivisor?: number;

  /** Chargeable-weight rounding step in kg (default 0.5); billing unit, not a base unit. */
  @IsOptional()
  @IsNumber()
  @Min(0.001)
  chargeableStepKg?: number;

  @IsOptional()
  @IsBoolean()
  weightRequired?: boolean;

  @IsOptional()
  @IsBoolean()
  mediumConfirmAllowed?: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  minDimensionCm?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  maxDimensionCm?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  idleAutoCompleteMinutes?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  photoRetentionMonths?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  localPurgeDays?: number;
}
