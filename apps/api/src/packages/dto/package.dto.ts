import {
  IsDateString,
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
 * Create a package (PRD §5–§7, §13). Base units only (mm, g); the server
 * computes every billing figure and the final package number — any billing
 * field sent by the client is ignored (CLAUDE.md rule 2). `id` is the
 * client-generated UUID (PRD §10) so a resend never duplicates.
 */
export class PackageCreateDto {
  @IsUUID()
  id!: string;

  @IsOptional()
  @IsInt()
  @Min(1)
  provisionalNumber?: number;

  @IsOptional()
  @IsUUID()
  stationId?: string;

  @IsOptional()
  @IsUUID()
  deviceId?: string;

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

  /**
   * Required when `weightSource = manual` (Team Leader / Admin only). Drives the
   * `manual_weight` flag and the audit reason (PRD §9).
   */
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

  @IsDateString()
  confirmedAt!: string;
}
