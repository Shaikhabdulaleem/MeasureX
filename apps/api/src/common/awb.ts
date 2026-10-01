import { BadRequestException } from '@nestjs/common';

/**
 * Normalise an AWB the way the scanner does: upper-case, no spaces (PRD §6).
 */
export function normaliseAwb(raw: string): string {
  return raw.replace(/\s+/g, '').toUpperCase();
}

/**
 * Validate an AWB against the configured regex (default `^AY\d{11}$`, PRD A1),
 * returning the normalised value. Throws 400 on mismatch — the only place an
 * AWB enters the system is a scan or manual entry, both validated here.
 */
export function assertValidAwb(raw: string, regex: string): string {
  const awb = normaliseAwb(raw);
  let re: RegExp;
  try {
    re = new RegExp(regex);
  } catch {
    // A misconfigured regex must not open the gate; fall back to the PRD default.
    re = /^AY\d{11}$/;
  }
  if (!re.test(awb)) {
    throw new BadRequestException({
      code: 'INVALID_AWB',
      message: 'AWB does not match the configured format',
      details: { awb },
    });
  }
  return awb;
}
