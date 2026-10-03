// Scale domain types shared by the adapters, the stability detector and the
// controller (PRD §9). Pure Dart — no Flutter imports — so it is unit-testable.

/// The scale states surfaced to the UI (PRD §9).
enum ScaleState {
  disconnected,
  connecting,
  connected,
  reading,
  unstable,
  stable,
  error,
}

/// One raw reading from a scale: a weight in grams and when it arrived. Base
/// units are integers (CLAUDE.md rule 1). [deviceStable] is the scale's own
/// stable flag when it reports one; the StabilityDetector is authoritative.
class ScaleReading {
  const ScaleReading({
    required this.grams,
    required this.timestamp,
    this.deviceStable,
  });

  final int grams;
  final DateTime timestamp;
  final bool? deviceStable;

  @override
  String toString() => 'ScaleReading(${grams}g @ ${timestamp.toIso8601String()})';
}

/// Per-model stability thresholds (PRD §9). Defaults match the PRD "stable
/// weight rule"; the server sends a scale's tuned values on the Scale record.
class ScaleThresholds {
  const ScaleThresholds({
    this.window = 5,
    this.toleranceG = 20,
    this.windowMs = 1500,
    this.minWeightG = 50,
    this.staleAfterMs = 5000,
  });

  /// Consecutive readings that must agree.
  final int window;

  /// Maximum spread (max − min, grams) across the window.
  final int toleranceG;

  /// Minimum time the window must span, in milliseconds.
  final int windowMs;

  /// Readings at or below this weight are treated as "nothing on the scale".
  final int minWeightG;

  /// A reading older than this (ms) is stale and must never be saved.
  final int staleAfterMs;

  factory ScaleThresholds.fromJson(Map<String, dynamic> json) => ScaleThresholds(
        window: (json['stabilityWindow'] as num?)?.toInt() ?? 5,
        toleranceG: (json['stabilityToleranceG'] as num?)?.toInt() ?? 20,
        windowMs: (json['stabilityWindowMs'] as num?)?.toInt() ?? 1500,
        minWeightG: (json['minWeightG'] as num?)?.toInt() ?? 50,
        staleAfterMs: (json['staleAfterMs'] as num?)?.toInt() ?? 5000,
      );
}
