import 'dart:async';

import '../scale_adapter.dart';
import '../scale_models.dart';
import '../weight_parser.dart';

/// HID keyboard-mode scale (PRD §9): the scale "types" the weight, usually
/// ending each reading with Enter, into a hidden focused field. The capture
/// screen feeds completed lines here via [submitLine]; the shared [WeightParser]
/// turns each line into grams. Universal fallback — works on Android and iOS.
class HidKeyboardScaleAdapter extends ScaleAdapter {
  HidKeyboardScaleAdapter({WeightParser parser = const WeightParser()}) : _parser = parser;

  final WeightParser _parser;
  final StreamController<ScaleReading> _controller = StreamController<ScaleReading>.broadcast();
  ScaleState _state = ScaleState.disconnected;

  @override
  ScaleAdapterInfo get info =>
      const ScaleAdapterInfo(key: 'hid', connection: 'hid', devOnly: false);

  @override
  String? get deviceLabel => 'HID keyboard scale';

  @override
  Future<void> connect() async {
    // "Connected" simply means the hidden field is focused and receiving input;
    // the owning screen is responsible for keeping focus.
    _state = ScaleState.connected;
  }

  @override
  Future<void> disconnect() async {
    _state = ScaleState.disconnected;
  }

  @override
  ScaleState status() => _state;

  @override
  Stream<ScaleReading> stream() => _controller.stream;

  /// Called by the UI when a full line (terminated by Enter) has been typed.
  void submitLine(String line) {
    if (_controller.isClosed) return;
    final reading = _parseLine(line);
    if (reading != null) {
      _state = ScaleState.reading;
      _controller.add(reading);
    }
  }

  ScaleReading? _parseLine(String line) {
    final parsed = _parser.parse(line);
    if (parsed == null) return null;
    return ScaleReading(
      grams: parsed.grams,
      timestamp: DateTime.now(),
      deviceStable: parsed.deviceStable,
    );
  }

  @override
  ScaleReading? parse(List<int> bytes) => _parseLine(String.fromCharCodes(bytes));

  @override
  Future<void> dispose() async {
    await _controller.close();
  }
}
