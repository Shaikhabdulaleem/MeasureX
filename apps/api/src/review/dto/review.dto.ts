import { ArrayNotEmpty, IsArray, IsEnum, IsOptional, IsString, IsUUID } from 'class-validator';
import { FlagType, RemeasureReason } from '@prisma/client';

/**
 * Create a flag. The Labour "Flag for Team Leader" action sends a shipmentId and
 * defaults to `worker_flag` (PRD §5). Other worker-relevant flag types are
 * accepted for forward use.
 */
export class FlagCreateDto {
  @IsOptional()
  @IsUUID()
  shipmentId?: string;

  @IsOptional()
  @IsUUID()
  packageId?: string;

  @IsOptional()
  @IsEnum(FlagType)
  type?: FlagType;

  @IsOptional()
  @IsString()
  note?: string;
}

/** Request a remeasurement (Team Leader / Admin). PRD §8, §11. */
export class RemeasureCreateDto {
  @IsUUID()
  shipmentId!: string;

  @IsArray()
  @ArrayNotEmpty()
  @IsUUID('all', { each: true })
  packageIds!: string[];

  @IsEnum(RemeasureReason)
  reason!: RemeasureReason;

  @IsOptional()
  @IsString()
  note?: string;
}
