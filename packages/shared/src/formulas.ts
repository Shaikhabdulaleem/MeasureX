/**
 * MeasureX billing formulas — the single source of truth (PRD §7, §14).
 *
 * The mobile app shows a preview and the server value is final, but BOTH import
 * these functions so they can never drift. Inputs are integer base units
 * (millimetres, grams); do not pass floats for base units.
 *
 * Worked example (PRD §7), which the tests pin:
 *   45.2 × 30.1 × 20.4 cm  (= 452 × 301 × 204 mm)
 *     → billing 46 × 31 × 21 cm
 *     → CBM 0.0299 m³
 *     → volumetric 5.99 kg (÷ 5000)
 *     → actual 4.8 kg  → chargeable 6.0 kg
 */

/** Small tolerance so float noise never bumps a value up a rounding step. */
const EPSILON = 1e-9;

export interface BillingInput {
  /** Measured length in millimetres (integer). */
  lengthMm: number;
  /** Measured width in millimetres (integer). */
  widthMm: number;
  /** Measured height in millimetres (integer). */
  heightMm: number;
  /** Actual (scale) weight in grams (integer), or null when not captured. */
  actualWeightG?: number | null;
  /** Volumetric divisor in cm/kg terms (default 5000, PRD A4). */
  divisor?: number;
  /** Chargeable-weight rounding step in kg (default 0.5, PRD A5). */
  chargeableStepKg?: number;
}

export interface BillingResult {
  /** Billing dimensions, each rounded up to the next whole cm. */
  billingLCm: number;
  billingWCm: number;
  billingHCm: number;
  /** Divisor actually used (saved on each package). */
  divisorUsed: number;
  /** CBM in m³, rounded to 4 decimals. */
  cbm: number;
  /** Volumetric weight in grams (integer), from the precise value. */
  volumetricG: number;
  /** Chargeable weight in grams (integer) = max(actual, volumetric) ↑ step. */
  chargeableG: number;
}

export const DEFAULT_DIVISOR = 5000;
export const DEFAULT_CHARGEABLE_STEP_KG = 0.5;

/** Ceil a millimetre value to the next whole centimetre: `L_cm = ⌈mm / 10⌉`. */
export function billingDimensionCm(mm: number): number {
  assertNonNegativeInt(mm, 'dimension (mm)');
  // mm is an integer; mm/10 has at most one decimal place, so ceil is exact.
  return Math.ceil(mm / 10);
}

/** CBM (m³) from whole-cm billing dimensions, rounded to 4 decimals. */
export function cbm(lCm: number, wCm: number, hCm: number): number {
  const raw = (lCm * wCm * hCm) / 1_000_000;
  return roundTo(raw, 4);
}

/**
 * Volumetric weight in kilograms from whole-cm billing dimensions:
 * `(L × W × H) / divisor`. Precise (not yet rounded to a gram).
 */
export function volumetricKg(
  lCm: number,
  wCm: number,
  hCm: number,
  divisor: number = DEFAULT_DIVISOR,
): number {
  if (divisor <= 0) throw new RangeError('divisor must be > 0');
  return (lCm * wCm * hCm) / divisor;
}

/** Round a kg value UP to the next multiple of `stepKg`. */
export function roundUpToStep(
  valueKg: number,
  stepKg: number = DEFAULT_CHARGEABLE_STEP_KG,
): number {
  if (stepKg <= 0) throw new RangeError('stepKg must be > 0');
  const steps = Math.ceil(valueKg / stepKg - EPSILON);
  return roundTo(steps * stepKg, 3);
}

/**
 * Chargeable weight in kilograms: round `max(actual, volumetric)` up to the
 * configured step. `actualKg`/`volumetricKg` are precise kg values.
 */
export function chargeableKg(
  actualKg: number,
  volumetricWeightKg: number,
  stepKg: number = DEFAULT_CHARGEABLE_STEP_KG,
): number {
  return roundUpToStep(Math.max(actualKg, volumetricWeightKg), stepKg);
}

/**
 * Compute every billing figure from integer base units. This is what the
 * server persists onto a `measurement_version`; the mobile app calls it for
 * the review-screen preview.
 */
export function computeBilling(input: BillingInput): BillingResult {
  const divisor = input.divisor ?? DEFAULT_DIVISOR;
  const stepKg = input.chargeableStepKg ?? DEFAULT_CHARGEABLE_STEP_KG;

  const billingLCm = billingDimensionCm(input.lengthMm);
  const billingWCm = billingDimensionCm(input.widthMm);
  const billingHCm = billingDimensionCm(input.heightMm);

  const cbmValue = cbm(billingLCm, billingWCm, billingHCm);

  const volKg = volumetricKg(billingLCm, billingWCm, billingHCm, divisor);
  const volumetricG = Math.round(volKg * 1000);

  const actualG = input.actualWeightG ?? 0;
  const actualKg = actualG / 1000;
  const chargeableG = Math.round(chargeableKg(actualKg, volKg, stepKg) * 1000);

  return {
    billingLCm,
    billingWCm,
    billingHCm,
    divisorUsed: divisor,
    cbm: cbmValue,
    volumetricG,
    chargeableG,
  };
}

// --- internal helpers -------------------------------------------------------

function roundTo(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round((value + EPSILON) * factor) / factor;
}

function assertNonNegativeInt(value: number, label: string): void {
  if (!Number.isInteger(value) || value < 0) {
    throw new RangeError(`${label} must be a non-negative integer, got ${value}`);
  }
}
