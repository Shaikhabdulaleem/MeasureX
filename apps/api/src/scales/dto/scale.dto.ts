import { IsBoolean, IsEnum, IsInt, IsOptional, IsString, Min, MinLength } from 'class-validator';
import { ScaleConnection } from '@prisma/client';

/**
 * Create a scale (PRD §9, §13 `/scales`). A scale is the approved-model record
 * that mobile adapters bind to; its stability thresholds drive the mobile
 * StabilityDetector so the capture flow never changes per model. Admin only.
 */
export class ScaleCreateDto {
  @IsString()
  @MinLength(1)
  model!: string;

  @IsEnum(ScaleConnection)
  connection!: ScaleConnection;

  /** Which mobile adapter handles this model (e.g. "simulated", "hid", "ble", "classic"). */
  @IsString()
  @MinLength(1)
  adapterKey!: string;

  @IsOptional()
  @IsBoolean()
  approved?: boolean;

  /** Streaming (continuous) vs one-shot. Defaults by connection (HID → one-shot). */
  @IsOptional()
  @IsBoolean()
  streaming?: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  stabilityWindow?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  stabilityToleranceG?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  stabilityWindowMs?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  minWeightG?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  staleAfterMs?: number;
}

/** Update a scale (e.g. mark approved, tune thresholds). Admin only. */
export class ScaleUpdateDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  model?: string;

  @IsOptional()
  @IsEnum(ScaleConnection)
  connection?: ScaleConnection;

  @IsOptional()
  @IsString()
  @MinLength(1)
  adapterKey?: string;

  @IsOptional()
  @IsBoolean()
  approved?: boolean;

  /** Streaming (continuous) vs one-shot. Defaults by connection (HID → one-shot). */
  @IsOptional()
  @IsBoolean()
  streaming?: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  stabilityWindow?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  stabilityToleranceG?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  stabilityWindowMs?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  minWeightG?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  staleAfterMs?: number;
}
