import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  ArrayMinSize,
  IsArray,
  IsDateString,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  MinLength,
  ValidateNested,
} from 'class-validator';

/**
 * A measurement telemetry event (PRD §12). Append-only; `id` is the
 * client-generated UUID so a replayed batch is deduplicated (skipDuplicates).
 */
export class MeasurementEventDto {
  @IsOptional()
  @IsUUID()
  id?: string;

  @IsOptional()
  @IsUUID()
  deviceId?: string;

  @IsOptional()
  @IsUUID()
  userId?: string;

  @IsOptional()
  @IsString()
  awb?: string;

  /** scan | measure_start | measure_ready | retake | confirm | manual_entry | scale_stable | … */
  @IsString()
  @MinLength(1)
  type!: string;

  @IsOptional()
  @IsObject()
  payload?: Record<string, unknown>;

  @IsDateString()
  occurredAt!: string;
}

/** POST /events/batch — upload telemetry (append-only, replay-safe). */
export class EventBatchDto {
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(200)
  @ValidateNested({ each: true })
  @Type(() => MeasurementEventDto)
  events!: MeasurementEventDto[];
}
