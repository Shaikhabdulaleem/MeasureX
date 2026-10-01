import { describe, it, expect } from 'vitest';
import {
  billingDimensionCm,
  cbm,
  volumetricKg,
  roundUpToStep,
  chargeableKg,
  computeBilling,
  DEFAULT_DIVISOR,
} from '../src/formulas';

describe('billingDimensionCm — ceil(mm / 10)', () => {
  it('rounds up to the next whole cm (worked example)', () => {
    expect(billingDimensionCm(452)).toBe(46); // 45.2 → 46
    expect(billingDimensionCm(301)).toBe(31); // 30.1 → 31
    expect(billingDimensionCm(204)).toBe(21); // 20.4 → 21
  });

  it('leaves exact whole-cm values unchanged', () => {
    expect(billingDimensionCm(450)).toBe(45);
    expect(billingDimensionCm(10)).toBe(1);
    expect(billingDimensionCm(0)).toBe(0);
  });

  it('rounds up even 0.1 mm over a boundary', () => {
    expect(billingDimensionCm(451)).toBe(46);
    expect(billingDimensionCm(459)).toBe(46);
  });

  it('rejects non-integer or negative input', () => {
    expect(() => billingDimensionCm(45.2)).toThrow(RangeError);
    expect(() => billingDimensionCm(-10)).toThrow(RangeError);
  });
});

describe('cbm — (L × W × H) / 1_000_000, 4 decimals', () => {
  it('matches the worked example (0.0299)', () => {
    expect(cbm(46, 31, 21)).toBe(0.0299); // 29946 / 1e6 = 0.029946
  });

  it('rounds to 4 decimals', () => {
    expect(cbm(100, 100, 100)).toBe(1); // 1_000_000 / 1e6
  });
});

describe('volumetricKg — (L × W × H) / divisor', () => {
  it('matches the worked example (5.9892, shown 5.99)', () => {
    expect(volumetricKg(46, 31, 21, DEFAULT_DIVISOR)).toBeCloseTo(5.9892, 4);
  });

  it('defaults to divisor 5000', () => {
    expect(volumetricKg(46, 31, 21)).toBeCloseTo(5.9892, 4);
  });

  it('throws on a non-positive divisor', () => {
    expect(() => volumetricKg(10, 10, 10, 0)).toThrow(RangeError);
  });
});

describe('roundUpToStep — round up to the next step', () => {
  it('rounds the worked example up to 6.0 kg (step 0.5)', () => {
    expect(roundUpToStep(5.9892, 0.5)).toBe(6.0);
  });

  it('leaves an exact multiple unchanged', () => {
    expect(roundUpToStep(6.0, 0.5)).toBe(6.0);
    expect(roundUpToStep(4.5, 0.5)).toBe(4.5);
  });

  it('rounds just over a step up to the next', () => {
    expect(roundUpToStep(4.51, 0.5)).toBe(5.0);
    expect(roundUpToStep(0.01, 0.5)).toBe(0.5);
  });

  it('supports a configurable step', () => {
    expect(roundUpToStep(5.9892, 1)).toBe(6.0);
    expect(roundUpToStep(5.1, 1)).toBe(6.0);
  });
});

describe('chargeableKg — max(actual, volumetric) ↑ step', () => {
  it('uses volumetric when it exceeds actual (worked example)', () => {
    // actual 4.8 kg, volumetric 5.9892 kg → 6.0 kg
    expect(chargeableKg(4.8, 5.9892, 0.5)).toBe(6.0);
  });

  it('uses actual when it exceeds volumetric', () => {
    expect(chargeableKg(10.2, 5.9892, 0.5)).toBe(10.5);
  });
});

describe('computeBilling — full pipeline from base units', () => {
  it('reproduces the PRD §7 worked example end to end', () => {
    const result = computeBilling({
      lengthMm: 452,
      widthMm: 301,
      heightMm: 204,
      actualWeightG: 4800,
      divisor: 5000,
      chargeableStepKg: 0.5,
    });

    expect(result).toEqual({
      billingLCm: 46,
      billingWCm: 31,
      billingHCm: 21,
      divisorUsed: 5000,
      cbm: 0.0299,
      volumetricG: 5989, // 5.9892 kg → 5989 g
      chargeableG: 6000, // 6.0 kg
    });
  });

  it('applies defaults (divisor 5000, step 0.5) when omitted', () => {
    const result = computeBilling({
      lengthMm: 452,
      widthMm: 301,
      heightMm: 204,
      actualWeightG: 4800,
    });
    expect(result.divisorUsed).toBe(5000);
    expect(result.chargeableG).toBe(6000);
  });

  it('treats a missing actual weight as 0 (volumetric wins)', () => {
    const result = computeBilling({
      lengthMm: 452,
      widthMm: 301,
      heightMm: 204,
      actualWeightG: null,
    });
    expect(result.chargeableG).toBe(6000);
  });

  it('lets a heavier actual weight drive the chargeable figure', () => {
    const result = computeBilling({
      lengthMm: 452,
      widthMm: 301,
      heightMm: 204,
      actualWeightG: 10200, // 10.2 kg
    });
    expect(result.chargeableG).toBe(10500); // 10.5 kg
  });
});
