import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  ArrayMinSize,
  IsArray,
  IsOptional,
  IsString,
  IsUUID,
  Matches,
  ValidateNested,
} from 'class-validator';
import { PackageCreateDto } from '../../packages/dto/package.dto';

/**
 * One package in a sync batch. Same shape as a single create (PRD §13) but each
 * item carries its own AWB, since a batch spans many shipments. The AWB is
 * validated against the configured regex in the service (per effective config),
 * so the pattern here is only a cheap shape guard.
 */
export class SyncPackageDto extends PackageCreateDto {
  @IsString()
  @Matches(/^[A-Za-z0-9]+$/, { message: 'awb must be alphanumeric' })
  awb!: string;

  /**
   * The user who measured this package on the device (PRD §3 shared phones).
   * The server rejects an item whose owner is not the caller (OWNER_MISMATCH),
   * so a device never uploads another user's pending records.
   */
  @IsOptional()
  @IsUUID()
  measuredBy?: string;
}

/** POST /sync/batch — up to 50 packages, idempotent per item (PRD §10, §13). */
export class SyncBatchDto {
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(50)
  @ValidateNested({ each: true })
  @Type(() => SyncPackageDto)
  packages!: SyncPackageDto[];
}
