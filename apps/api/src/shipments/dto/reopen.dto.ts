import { IsString, MinLength } from 'class-validator';

/** Reopen a completed shipment (PRD §8). Reason is mandatory and audited. */
export class ReopenDto {
  @IsString()
  @MinLength(1)
  reason!: string;
}
