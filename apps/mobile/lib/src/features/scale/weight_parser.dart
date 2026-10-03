/// Parses a scale's text/byte output into grams (PRD §9 `parse(bytes)`).
///
/// A single pluggable parser handles the common formats so a new scale model
/// drops in without touching the capture flow:
///   - "12.34 kg" / "12,34 kg"   → 12340 g
///   - "12340 g"                 → 12340 g
///   - "1234.5" (bare, grams)    → 1235 g   (assumed grams when no unit)
///   - "ST,GS,  12.34kg"         → 12340 g  (Toledo/CAS style frames)
///   - "US,NT,  0.517 kg"        → 517 g    (unstable frame; stability flag parsed)
///
/// Returns null when no weight can be found.
class ParsedWeight {
  const ParsedWeight({required this.grams, this.deviceStable});

  final int grams;

  /// The scale's own stable/unstable flag when the frame carries one
  /// (e.g. "ST" = stable, "US" = unstable). Null when absent.
  final bool? deviceStable;
}

class WeightParser {
  const WeightParser();

  // A signed decimal number, optionally followed by a unit.
  static final RegExp _numberUnit = RegExp(
    r'(-?\d+(?:[.,]\d+)?)\s*(kg|g|lb)?',
    caseSensitive: false,
  );

  ParsedWeight? parse(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return null;

    final deviceStable = _deviceStableFlag(text);

    // Pick the LAST number in the frame: status-prefixed frames (e.g.
    // "ST,GS,12.34kg") put the weight at the end, after tare/gross codes.
    final matches = _numberUnit.allMatches(text).toList();
    if (matches.isEmpty) return null;
    final match = matches.last;

    final numberText = match.group(1)!.replaceAll(',', '.');
    final value = double.tryParse(numberText);
    if (value == null) return null;

    final unit = match.group(2)?.toLowerCase();
    final int grams;
    switch (unit) {
      case 'kg':
        grams = (value * 1000).round();
        break;
      case 'lb':
        grams = (value * 453.59237).round();
        break;
      case 'g':
        grams = value.round();
        break;
      default:
        // No unit: a decimal value is read as kilograms (most HID scales type
        // "12.34"); a plain integer is read as grams.
        grams = numberText.contains('.') ? (value * 1000).round() : value.round();
    }
    return ParsedWeight(grams: grams, deviceStable: deviceStable);
  }

  /// Detect an ST/US stability token in a status frame, if present.
  bool? _deviceStableFlag(String text) {
    final upper = text.toUpperCase();
    final hasSt = RegExp(r'(^|[,\s])ST([,\s]|$)').hasMatch(upper);
    final hasUs = RegExp(r'(^|[,\s])US([,\s]|$)').hasMatch(upper);
    if (hasSt) return true;
    if (hasUs) return false;
    return null;
  }
}
