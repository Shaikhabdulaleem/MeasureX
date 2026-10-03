import {
  ArrayNotEmpty,
  IsArray,
  IsEnum,
  IsIn,
  IsOptional,
  IsString,
  IsUUID,
  MinLength,
  ValidateIf,
} from 'class-validator';
import { Role } from '@prisma/client';

/**
 * Create a user (Admin only, PRD §3). A new user always starts with
 * `mustChangePassword = true` (first login forces a change). If no `password`
 * is supplied the server generates a temporary one and returns it once so the
 * Admin can hand it over.
 */
export class UserCreateDto {
  @IsString()
  @MinLength(1)
  employeeId!: string;

  @IsString()
  @MinLength(1)
  name!: string;

  @IsEnum(Role)
  role!: Role;

  @IsUUID()
  homeBranchId!: string;

  /**
   * Admin scope: an array of branch ids, or ["all"]. Required for admins,
   * ignored for other roles.
   */
  @ValidateIf((o) => o.role === Role.admin)
  @IsArray()
  @ArrayNotEmpty()
  @IsString({ each: true })
  adminScope?: string[];

  @IsOptional()
  @IsString()
  @MinLength(8)
  password?: string;
}

/** Update a user (Admin only). Employee id is immutable once assigned. */
export class UserUpdateDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  name?: string;

  @IsOptional()
  @IsEnum(Role)
  role?: Role;

  @IsOptional()
  @IsUUID()
  homeBranchId?: string;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  adminScope?: string[];

  @IsOptional()
  @IsIn(['active', 'inactive'])
  status?: 'active' | 'inactive';
}

/** Optional explicit temp password on reset; otherwise the server generates one. */
export class UserResetPasswordDto {
  @IsOptional()
  @IsString()
  @MinLength(8)
  password?: string;
}
