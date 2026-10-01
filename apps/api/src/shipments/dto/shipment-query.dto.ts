import { Type } from 'class-transformer';
import { IsEnum, IsInt, IsISO8601, IsOptional, IsString, IsUUID, Max, Min } from 'class-validator';
import { Confidence, FlagType, MeasurementMethod, ShipmentStatus } from '@prisma/client';

/** Query parameters for GET /shipments (filters + cursor pagination). */
export class ShipmentQueryDto {
  @IsOptional()
  @IsUUID()
  branchId?: string;

  @IsOptional()
  @IsEnum(ShipmentStatus)
  status?: ShipmentStatus;

  @IsOptional()
  @IsISO8601()
  dateFrom?: string;

  @IsOptional()
  @IsISO8601()
  dateTo?: string;

  /** Filter to shipments measured by this employee (user id). */
  @IsOptional()
  @IsUUID()
  employeeId?: string;

  @IsOptional()
  @IsEnum(Confidence)
  confidence?: Confidence;

  @IsOptional()
  @IsEnum(MeasurementMethod)
  method?: MeasurementMethod;

  @IsOptional()
  @IsEnum(FlagType)
  flag?: FlagType;

  /** Free-text AWB filter (contains, case-insensitive). */
  @IsOptional()
  @IsString()
  awb?: string;

  @IsOptional()
  @IsString()
  cursor?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(200)
  limit?: number;
}
