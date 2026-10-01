import { IsEnum, IsInt, IsOptional, IsString, Min } from 'class-validator';
import { PhotoKind } from '@prisma/client';

/** Request a signed upload URL for a package photo (PRD §6, §13). */
export class PhotoUploadRequestDto {
  @IsOptional()
  @IsEnum(PhotoKind)
  kind?: PhotoKind;

  @IsString()
  contentType!: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  bytes?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  width?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  height?: number;
}
