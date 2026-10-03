import {
  ArrayNotEmpty,
  IsArray,
  IsEnum,
  IsIn,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { FlagStatus, FlagType, RemeasureReason } from '@prisma/client';

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

/** Filters for GET /flags (Team Leader / Admin review queue, PRD §11). */
export class FlagQueryDto {
  @IsOptional()
  @IsEnum(FlagStatus)
  status?: FlagStatus;

  @IsOptional()
  @IsEnum(FlagType)
  type?: FlagType;

  @IsOptional()
  @IsString()
  awb?: string;

  @IsOptional()
  @IsUUID()
  cursor?: string;

  @IsOptional()
  @IsString()
  limit?: string;
}

/**
 * Resolve a flag (PRD §11): `approve` accepts it, `dismiss` rejects it — both
 * close the flag with an optional note. The distinction is preserved in the
 * flag status (`resolved` vs `dismissed`) and the audit entry.
 */
export class FlagResolveDto {
  @IsIn(['approve', 'dismiss'])
  action!: 'approve' | 'dismiss';

  @IsOptional()
  @IsString()
  note?: string;
}
