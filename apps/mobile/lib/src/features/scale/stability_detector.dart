import 'scale_models.dart';

/// Outcome of feeding a reading to the [StabilityDetector].
class StabilityResult {
  const StabilityResult({
    required this.phase,
    required this.grams,
    required this.stable,
    required this.stale,
    required this.spreadG,
  });

  /// One of [ScaleState.reading], [ScaleState.unstable] or [ScaleState.stable].
  final ScaleState phase;

  /// The weight to show/save: the window median when stable, else the latest
  /// reading. Null when there are no readings.
  final int? grams;

  /// True only when the stable-weight rule is fully satisfied (PRD §9).
  final bool stable;

  /// True when the latest reading is older than [ScaleThresholds.staleAfterMs].
  final bool stale;

  /// Current spread (max − min, grams) across the window.
  final int spreadG;

  static const empty = StabilityResult(
    phase: ScaleState.reading,
    grams: null,
    stable: false,
    stale: false,
    spreadG: 0,
  );
}

/// Decides when a scale reading is stable (PRD §9), as a pure, deterministic
/// function of the readings it is fed — no timers — so it is fully unit-tested.
///
/// Stable = [ScaleThresholds.window] consecutive readings whose spread is within
/// [ScaleThresholds.toleranceG], spanning at least [ScaleThresholds.windowMs],
/// with a value above [ScaleThresholds.minWeightG]. A reading older than
/// [ScaleThresholds.staleAfterMs] is stale and can never be stable.
class StabilityDetector {
  StabilityDetector(this.thresholds);

  final ScaleThresholds thresholds;
  final List<ScaleReading> _window = <ScaleReading>[];

  /// Clear all buffered readings (e.g. on disconnect) so a stale stable value
  /// can never carry over into a new session.
  void reset() => _window.clear();

  /// Feed a reading. [now] defaults to the reading's timestamp; pass it to
  /// evaluate staleness against the current clock.
  StabilityResult add(ScaleReading reading, {DateTime? now}) {
    final at = now ?? reading.timestamp;
    _window.add(reading);
    return _evaluate(at);
  }

  /// Re-evaluate the buffered readings against [now] without adding one (used
  /// to detect that a previously stable value has gone stale).
  StabilityResult evaluate(DateTime now) => _evaluate(now);

  StabilityResult _evaluate(DateTime now) {
    if (_window.isEmpty) return StabilityResult.empty;

    final latest = _window.last;

    // Nothing on the scale → never stable, and the value is cleared (PRD §9).
    // For a one-shot scale this is also how a settled value is released.
    if (latest.grams <= thresholds.minWeightG) {
      _window.clear();
      return const StabilityResult(
        phase: ScaleState.reading,
        grams: null,
        stable: false,
        stale: false,
        spreadG: 0,
      );
    }

    // Staleness applies to STREAMING scales only; a one-shot value persists
    // until the next reading, a drop below minWeightG, or disconnect.
    final latestAgeMs = now.difference(latest.timestamp).inMilliseconds;
    final stale = thresholds.streaming && latestAgeMs > thresholds.staleAfterMs;

    // The scale's own stability flag wins when present (PRD §9): ST → stable,
    // US → never stable; only fall back to the window rule when it is absent.
    final deviceFlag = latest.deviceStable;

    // Drop readings (except the latest) that have aged past the stale horizon so
    // a long gap can never form a false "consecutive" window; bound to `window`.
    _window.removeWhere(
      (r) =>
          !identical(r, latest) &&
          now.difference(r.timestamp).inMilliseconds > thresholds.staleAfterMs,
    );
    if (_window.length > thresholds.window) {
      _window.removeRange(0, _window.length - thresholds.window);
    }

    final recent = _window;
    final grams = recent.map((r) => r.grams).toList();
    final minG = grams.reduce((a, b) => a < b ? a : b);
    final maxG = grams.reduce((a, b) => a > b ? a : b);
    final spreadG = maxG - minG;
    final median = _median(grams);
    final spanMs =
        recent.last.timestamp.difference(recent.first.timestamp).inMilliseconds;

    final hasEnough = recent.length >= thresholds.window;
    final withinTolerance = spreadG <= thresholds.toleranceG;
    final longEnough = spanMs >= thresholds.windowMs;

    // Decide stability. Device flag first; then one-shot (a settled line is
    // stable on its own); else the streaming window rule.
    final bool stableCandidate;
    final bool windowRuleUsed;
    if (deviceFlag == true) {
      stableCandidate = true;
      windowRuleUsed = false;
    } else if (deviceFlag == false) {
      stableCandidate = false;
      windowRuleUsed = false;
    } else if (!thresholds.streaming) {
      stableCandidate = true; // one-shot: this reading is the settled value
      windowRuleUsed = false;
    } else {
      stableCandidate = hasEnough && withinTolerance && longEnough;
      windowRuleUsed = true;
    }

    final stable = stableCandidate && !stale;
    // Average out jitter only when the streaming window rule produced it.
    final chosenGrams = stable && windowRuleUsed ? median : latest.grams;

    final ScaleState phase;
    if (stable) {
      phase = ScaleState.stable;
    } else if (deviceFlag == false || (windowRuleUsed && hasEnough && !withinTolerance)) {
      phase = ScaleState.unstable;
    } else {
      phase = ScaleState.reading;
    }

    return StabilityResult(
      phase: phase,
      grams: stable ? chosenGrams : latest.grams,
      stable: stable,
      stale: stale,
      spreadG: spreadG,
    );
  }

  static int _median(List<int> values) {
    final sorted = List<int>.from(values)..sort();
    final mid = sorted.length ~/ 2;
    if (sorted.length.isOdd) return sorted[mid];
    return ((sorted[mid - 1] + sorted[mid]) / 2).round();
  }
}
