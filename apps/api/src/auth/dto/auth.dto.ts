import { IsOptional, IsString, MinLength } from 'class-validator';

export class LoginDto {
  @IsString()
  employeeId!: string;

  @IsString()
  password!: string;

  @IsOptional()
  @IsString()
  installId?: string;
}

export class RefreshDto {
  @IsString()
  refreshToken!: string;
}

export class LogoutDto {
  @IsOptional()
  @IsString()
  refreshToken?: string;
}

export class ChangePasswordDto {
  @IsString()
  currentPassword!: string;

  @IsString()
  @MinLength(8)
  newPassword!: string;
}
