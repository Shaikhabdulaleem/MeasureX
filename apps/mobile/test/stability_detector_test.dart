import 'package:flutter_test/flutter_test.dart';
import 'package:measurex/src/features/scale/scale_models.dart';
import 'package:measurex/src/features/scale/stability_detector.dart';

/// PRD §9 stable-weight rule: 5 consecutive readings within ±20 g over ≥ 1.5 s,
/// value > 50 g; a reading older than 5 s is stale.
void main() {
  const thresholds = ScaleThresholds(
    window: 5,
    toleranceG: 20,
    windowMs: 1500,
    minWeightG: 50,
    staleAfterMs: 5000,
  );

  final t0 = DateTime(2026, 1, 1, 12, 0, 0);

  /// Feed [values] spaced [stepMs] apart; returns the last result.
  StabilityResult feed(
    StabilityDetector d,
    List<int> values, {
    int stepMs = 400,
    DateTime? start,
  }) {
    final base = start ?? t0;
    late StabilityResult result;
    for (var i = 0; i < values.length; i++) {
      final at = base.add(Duration(milliseconds: stepMs * i));
      result = d.add(ScaleReading(grams: values[i], timestamp: at), now: at);
    }
    return result;
  }

  test('stable: 5 readings within tolerance over ≥ 1.5 s above 50 g', () {
    final d = StabilityDetector(thresholds);
    final r = feed(d, [4800, 4805, 4798, 4802, 4801]); // span 1600 ms, spread 7 g
    expect(r.stable, isTrue);
    expect(r.phase, ScaleState.stable);
    expect(r.grams, 4801); // median
    expect(r.stale, isFalse);
  });

  test('unstable: spread exceeds tolerance', () {
    final d = StabilityDetector(thresholds);
    final r = feed(d, [4800, 4700, 4900, 4600, 5000]); // spread 400 g
    expect(r.stable, isFalse);
    expect(r.phase, ScaleState.unstable);
  });

  test('not stable when the window is shorter than 1.5 s', () {
    final d = StabilityDetector(thresholds);
    final r = feed(d, [4800, 4801, 4802, 4803, 4804], stepMs: 200); // span 800 ms
    expect(r.stable, isFalse);
  });

  test('below 50 g is never stable (nothing on the scale)', () {
    final d = StabilityDetector(thresholds);
    final r = feed(d, [10, 12, 11, 13, 10]);
    expect(r.stable, isFalse);
    expect(r.phase, ScaleState.reading);
  });

  test('stale: a reading older than 5 s cannot be stable', () {
    final d = StabilityDetector(thresholds);
    feed(d, [4800, 4805, 4798, 4802, 4801]);
    // Re-evaluate 6 s after the last reading.
    final later = t0.add(const Duration(milliseconds: 400 * 4 + 6000));
    final r = d.evaluate(later);
    expect(r.stale, isTrue);
    expect(r.stable, isFalse);
  });

  test('disconnect mid-read: reset clears any prior stability', () {
    final d = StabilityDetector(thresholds);
    final stable = feed(d, [4800, 4805, 4798, 4802, 4801]);
    expect(stable.stable, isTrue);

    d.reset(); // controller calls this on disconnect

    // A single fresh reading after reset is not stable again.
    final after = d.add(
      ScaleReading(grams: 4801, timestamp: t0.add(const Duration(seconds: 10))),
      now: t0.add(const Duration(seconds: 10)),
    );
    expect(after.stable, isFalse);
  });

  group('device stability flag (PRD §9)', () {
    test('a single "ST" reading is stable immediately (12340 g)', () {
      final d = StabilityDetector(thresholds);
      final r = d.add(
        ScaleReading(grams: 12340, timestamp: t0, deviceStable: true),
        now: t0,
      );
      expect(r.stable, isTrue);
      expect(r.grams, 12340);
    });

    test('a "US" reading is never stable even if steady', () {
      final d = StabilityDetector(thresholds);
      late StabilityResult r;
      for (var i = 0; i < 6; i++) {
        final at = t0.add(Duration(milliseconds: 400 * i));
        r = d.add(
          ScaleReading(grams: 12340, timestamp: at, deviceStable: false),
          now: at,
        );
      }
      expect(r.stable, isFalse);
      expect(r.phase, ScaleState.unstable);
    });

    test('an "ST" reading below 50 g is still not stable', () {
      final d = StabilityDetector(thresholds);
      final r = d.add(
        ScaleReading(grams: 10, timestamp: t0, deviceStable: true),
        now: t0,
      );
      expect(r.stable, isFalse);
    });
  });

  group('one-shot scales (HID / settle-then-send)', () {
    const oneShot = ScaleThresholds(
      window: 5,
      toleranceG: 20,
      windowMs: 1500,
      minWeightG: 50,
      staleAfterMs: 5000,
      streaming: false,
    );

    test('a single reading is stable, and stays valid after 30 s', () {
      final d = StabilityDetector(oneShot);
      final r = d.add(ScaleReading(grams: 12340, timestamp: t0), now: t0);
      expect(r.stable, isTrue);
      expect(r.grams, 12340);

      // No new reading for 30 s — the settled value persists (not stale).
      final later = d.evaluate(t0.add(const Duration(seconds: 30)));
      expect(later.stable, isTrue);
      expect(later.grams, 12340);
      expect(later.stale, isFalse);
    });

    test('a reading below 50 g clears the value', () {
      final d = StabilityDetector(oneShot);
      final stable = d.add(ScaleReading(grams: 12340, timestamp: t0), now: t0);
      expect(stable.stable, isTrue);

      final cleared = d.add(
        ScaleReading(grams: 0, timestamp: t0.add(const Duration(seconds: 5))),
        now: t0.add(const Duration(seconds: 5)),
      );
      expect(cleared.stable, isFalse);
      expect(cleared.grams, isNull);
    });
  });
}
