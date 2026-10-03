import { IsBoolean, IsEnum, IsOptional, IsString } from 'class-validator';
import { DeviceTier } from '@prisma/client';

/** Register a device + its tier-check result (PRD §4, §13). */
export class DeviceRegisterDto {
  @IsString()
  installId!: string;

  @IsOptional()
  @IsString()
  manufacturer?: string;

  @IsOptional()
  @IsString()
  model?: string;

  @IsOptional()
  @IsString()
  os?: string;

  @IsOptional()
  @IsString()
  osVersion?: string;

  @IsEnum(DeviceTier)
  tier!: DeviceTier;
}

/** Block / unblock a device (Admin, PRD §10). Defaults to blocking. */
export class DeviceBlockDto {
  @IsOptional()
  @IsBoolean()
  blocked?: boolean;
}
