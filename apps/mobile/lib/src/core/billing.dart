/// MeasureX billing formulas — Dart port of `packages/shared/src/formulas.ts`.
///
/// The server value is final; this port drives the **review-screen preview only**
/// (CLAUDE.md rule 2). It must stay in lock-step with the TypeScript source —
/// `test/billing_test.dart` pins the same PRD §7 worked examples the TS tests do.
///
/// Inputs are integer base units (millimetres, grams); never pass floats for
/// base units.
library;

import 'dart:math' as math;

const int kDefaultDivisor = 5000;
const double kDefaultChargeableStepKg = 0.5;

/// Small tolerance so float noise never bumps a value up a rounding step.
const double _epsilon = 1e-9;

class BillingResult {
  const BillingResult({
    required this.billingLCm,
    required this.billingWCm,
    required this.billingHCm,
    required this.divisorUsed,
    required this.cbm,
    required this.volumetricG,
    required this.chargeableG,
  });

  final int billingLCm;
  final int billingWCm;
  final int billingHCm;
  final int divisorUsed;

  /// CBM in m³, rounded to 4 decimals.
  final double cbm;

  /// Volumetric weight in grams (integer).
  final int volumetricG;

  /// Chargeable weight in grams (integer) = max(actual, volumetric) ↑ step.
  final int chargeableG;
}

/// Ceil a millimetre value to the next whole centimetre: `L_cm = ⌈mm / 10⌉`.
int billingDimensionCm(int mm) {
  if (mm < 0) {
    throw ArgumentError.value(mm, 'mm', 'dimension must be non-negative');
  }
  return (mm / 10).ceil();
}

/// CBM (m³) from whole-cm billing dimensions, rounded to 4 decimals.
double cbm(int lCm, int wCm, int hCm) {
  final raw = (lCm * wCm * hCm) / 1000000;
  return _roundTo(raw, 4);
}

/// Volumetric weight in kilograms: `(L × W × H) / divisor`. Precise (kg).
double volumetricKg(int lCm, int wCm, int hCm, [int divisor = kDefaultDivisor]) {
  if (divisor <= 0) throw ArgumentError.value(divisor, 'divisor', 'must be > 0');
  return (lCm * wCm * hCm) / divisor;
}

/// Round a kg value UP to the next multiple of [stepKg].
double roundUpToStep(double valueKg, [double stepKg = kDefaultChargeableStepKg]) {
  if (stepKg <= 0) throw ArgumentError.value(stepKg, 'stepKg', 'must be > 0');
  final steps = (valueKg / stepKg - _epsilon).ceil();
  return _roundTo(steps * stepKg, 3);
}

/// Chargeable weight (kg): round `max(actual, volumetric)` up to the step.
double chargeableKg(
  double actualKg,
  double volumetricWeightKg, [
  double stepKg = kDefaultChargeableStepKg,
]) {
  return roundUpToStep(math.max(actualKg, volumetricWeightKg), stepKg);
}

/// Compute every billing figure from integer base units (preview).
BillingResult computeBilling({
  required int lengthMm,
  required int widthMm,
  required int heightMm,
  int? actualWeightG,
  int divisor = kDefaultDivisor,
  double chargeableStepKg = kDefaultChargeableStepKg,
}) {
  final billingLCm = billingDimensionCm(lengthMm);
  final billingWCm = billingDimensionCm(widthMm);
  final billingHCm = billingDimensionCm(heightMm);

  final cbmValue = cbm(billingLCm, billingWCm, billingHCm);

  final volKg = volumetricKg(billingLCm, billingWCm, billingHCm, divisor);
  final volumetricG = (volKg * 1000).round();

  final actualG = actualWeightG ?? 0;
  final actualKg = actualG / 1000;
  final chargeableG = (chargeableKg(actualKg, volKg, chargeableStepKg) * 1000).round();

  return BillingResult(
    billingLCm: billingLCm,
    billingWCm: billingWCm,
    billingHCm: billingHCm,
    divisorUsed: divisor,
    cbm: cbmValue,
    volumetricG: volumetricG,
    chargeableG: chargeableG,
  );
}

double _roundTo(double value, int decimals) {
  final factor = math.pow(10, decimals);
  return ((value + _epsilon) * factor).round() / factor;
}
