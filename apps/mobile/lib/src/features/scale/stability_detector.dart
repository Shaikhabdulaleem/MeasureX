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

    // Staleness is a property of the LATEST reading, so decide it before any
    // pruning (otherwise an idle scale would empty the buffer and hide it).
    final latest = _window.last;
    final latestAgeMs = now.difference(latest.timestamp).inMilliseconds;
    final stale = latestAgeMs > thresholds.staleAfterMs;

    // Drop readings (except the latest) that have aged past the stale horizon,
    // so a long gap can never be treated as a consecutive window. Then keep the
    // buffer bounded to the most recent `window` readings.
    _window.removeWhere(
      (r) => !identical(r, latest) && now.difference(r.timestamp).inMilliseconds > thresholds.staleAfterMs,
    );
    if (_window.length > thresholds.window) {
      _window.removeRange(0, _window.length - thresholds.window);
    }

    // Consider only the most recent `window` readings for the stability test.
    final recent = _window.length <= thresholds.window
        ? List<ScaleReading>.from(_window)
        : _window.sublist(_window.length - thresholds.window);

    final grams = recent.map((r) => r.grams).toList();
    final minG = grams.reduce((a, b) => a < b ? a : b);
    final maxG = grams.reduce((a, b) => a > b ? a : b);
    final spreadG = maxG - minG;
    final median = _median(grams);
    final spanMs = recent.last.timestamp.difference(recent.first.timestamp).inMilliseconds;

    final hasEnough = recent.length >= thresholds.window;
    final withinTolerance = spreadG <= thresholds.toleranceG;
    final longEnough = spanMs >= thresholds.windowMs;
    final aboveMin = median > thresholds.minWeightG;

    final stable = !stale && hasEnough && withinTolerance && longEnough && aboveMin;

    final ScaleState phase;
    if (stable) {
      phase = ScaleState.stable;
    } else if (recent.length >= 2 && !withinTolerance) {
      phase = ScaleState.unstable;
    } else {
      phase = ScaleState.reading;
    }

    return StabilityResult(
      phase: phase,
      grams: stable ? median : latest.grams,
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
