import 'package:flutter_test/flutter_test.dart';
import 'package:measurex/src/features/scale/weight_parser.dart';

/// Parser covers the common scale output formats (PRD §9 `parse`).
void main() {
  const parser = WeightParser();

  test('parses "12.34 kg" → 12340 g', () {
    expect(parser.parse('12.34 kg')?.grams, 12340);
  });

  test('parses comma decimal "12,34 kg" → 12340 g', () {
    expect(parser.parse('12,34 kg')?.grams, 12340);
  });

  test('parses "12340 g" → 12340 g', () {
    expect(parser.parse('12340 g')?.grams, 12340);
  });

  test('parses a Toledo/CAS status frame "ST,GS,  12.34kg"', () {
    final r = parser.parse('ST,GS,  12.34kg');
    expect(r?.grams, 12340);
    expect(r?.deviceStable, isTrue);
  });

  test('parses an unstable frame "US,NT, 0.517 kg"', () {
    final r = parser.parse('US,NT, 0.517 kg');
    expect(r?.grams, 517);
    expect(r?.deviceStable, isFalse);
  });

  test('bare decimal with no unit is read as kilograms', () {
    expect(parser.parse('0.517')?.grams, 517);
  });

  test('bare integer with no unit is read as grams', () {
    expect(parser.parse('517')?.grams, 517);
  });

  test('handles a trailing newline (HID Enter)', () {
    expect(parser.parse('12.34 kg\r\n')?.grams, 12340);
  });

  test('returns null for junk with no number', () {
    expect(parser.parse('----'), isNull);
    expect(parser.parse(''), isNull);
  });
}
