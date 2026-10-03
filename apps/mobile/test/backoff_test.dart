import 'dart:math';
import 'package:flutter_test/flutter_test.dart';
import 'package:measurex/src/features/sync/backoff.dart';

void main() {
  group('nextBackoff', () {
    test('grows roughly exponentially and is capped', () {
      // No jitter for a deterministic check.
      Duration b(int a) => nextBackoff(a, jitterFraction: 0, base: const Duration(seconds: 2));
      expect(b(1), const Duration(seconds: 2));
      expect(b(2), const Duration(seconds: 4));
      expect(b(3), const Duration(seconds: 8));
      expect(b(4), const Duration(seconds: 16));
      // Capped at 5 minutes.
      expect(b(20), const Duration(minutes: 5));
      expect(b(40), const Duration(minutes: 5));
    });

    test('never negative and within the jittered cap', () {
      final rng = Random(42);
      for (var a = 1; a <= 50; a++) {
        final d = nextBackoff(a, rng: rng);
        expect(d.inMilliseconds, greaterThanOrEqualTo(0));
        // Max is 5 min + 20% jitter.
        expect(d.inMilliseconds, lessThanOrEqualTo((5 * 60 * 1000 * 1.2).round()));
      }
    });

    test('attempt < 1 is treated as attempt 1', () {
      expect(nextBackoff(0, jitterFraction: 0), nextBackoff(1, jitterFraction: 0));
    });
  });
}
