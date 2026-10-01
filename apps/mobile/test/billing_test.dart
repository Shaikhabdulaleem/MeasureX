import 'package:flutter_test/flutter_test.dart';
import 'package:measurex/src/core/billing.dart';

/// Parity with packages/shared/test/formulas.test.ts — the Dart preview must
/// produce exactly the server's numbers (PRD §7 worked example).
void main() {
  group('billingDimensionCm — ceil(mm / 10)', () {
    test('rounds up to the next whole cm (worked example)', () {
      expect(billingDimensionCm(452), 46);
      expect(billingDimensionCm(301), 31);
      expect(billingDimensionCm(204), 21);
    });

    test('leaves exact whole-cm values unchanged', () {
      expect(billingDimensionCm(450), 45);
      expect(billingDimensionCm(10), 1);
      expect(billingDimensionCm(0), 0);
    });

    test('rounds up even 0.1 mm over a boundary', () {
      expect(billingDimensionCm(451), 46);
      expect(billingDimensionCm(459), 46);
    });
  });

  group('cbm', () {
    test('matches the worked example (0.0299)', () {
      expect(cbm(46, 31, 21), 0.0299);
    });
    test('rounds to 4 decimals', () {
      expect(cbm(100, 100, 100), 1);
    });
  });

  group('volumetricKg', () {
    test('matches the worked example (5.9892)', () {
      expect(volumetricKg(46, 31, 21, kDefaultDivisor), closeTo(5.9892, 1e-4));
    });
  });

  group('roundUpToStep', () {
    test('rounds the worked example up to 6.0 kg (step 0.5)', () {
      expect(roundUpToStep(5.9892, 0.5), 6.0);
    });
    test('leaves an exact multiple unchanged', () {
      expect(roundUpToStep(6.0, 0.5), 6.0);
      expect(roundUpToStep(4.5, 0.5), 4.5);
    });
    test('rounds just over a step up to the next', () {
      expect(roundUpToStep(4.51, 0.5), 5.0);
      expect(roundUpToStep(0.01, 0.5), 0.5);
    });
  });

  group('computeBilling — full pipeline', () {
    test('reproduces the PRD §7 worked example end to end', () {
      final r = computeBilling(
        lengthMm: 452,
        widthMm: 301,
        heightMm: 204,
        actualWeightG: 4800,
        divisor: 5000,
        chargeableStepKg: 0.5,
      );
      expect(r.billingLCm, 46);
      expect(r.billingWCm, 31);
      expect(r.billingHCm, 21);
      expect(r.divisorUsed, 5000);
      expect(r.cbm, 0.0299);
      expect(r.volumetricG, 5989);
      expect(r.chargeableG, 6000);
    });

    test('treats a missing actual weight as 0 (volumetric wins)', () {
      final r = computeBilling(lengthMm: 452, widthMm: 301, heightMm: 204);
      expect(r.chargeableG, 6000);
    });

    test('lets a heavier actual weight drive the chargeable figure', () {
      final r = computeBilling(
        lengthMm: 452,
        widthMm: 301,
        heightMm: 204,
        actualWeightG: 10200,
      );
      expect(r.chargeableG, 10500);
    });
  });
}
