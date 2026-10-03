import 'dart:math';

/// Exponential backoff for failed sync attempts (PRD §10 rule 5). Pure and
/// deterministic given [attempt] and [rng], so it is unit-testable.
///
/// Attempt 1 → ~base, doubling each attempt, capped at [max]. A small +/- jitter
/// (±[jitterFraction]) spreads retries so many devices don't reconnect in sync.
/// The result is always within [base/2, max + jitter] and never negative.
Duration nextBackoff(
  int attempt, {
  Duration base = const Duration(seconds: 2),
  Duration max = const Duration(minutes: 5),
  double jitterFraction = 0.2,
  Random? rng,
}) {
  final a = attempt < 1 ? 1 : attempt;
  // 2^(a-1) * base, clamped to max (guard against overflow for large a).
  final exp = a > 40 ? max.inMilliseconds : base.inMilliseconds * (1 << (a - 1));
  final cappedMs = min(exp, max.inMilliseconds);

  final r = rng ?? Random();
  // Jitter in [-jitterFraction, +jitterFraction].
  final jitter = (r.nextDouble() * 2 - 1) * jitterFraction;
  final withJitter = (cappedMs * (1 + jitter)).round();

  return Duration(milliseconds: withJitter < 0 ? 0 : withJitter);
}
