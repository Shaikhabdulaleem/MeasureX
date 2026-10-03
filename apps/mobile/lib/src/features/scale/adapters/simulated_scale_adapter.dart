import 'dart:async';

import '../scale_adapter.dart';
import '../scale_models.dart';

/// A fake scale for tests and demos (dev builds only). It emits a burst of
/// unstable readings and then settles on a stable target, and can be told to
/// drop the connection mid-reading to prove that no value is ever saved from a
/// disconnected scale (PRD §9).
class SimulatedScaleAdapter extends ScaleAdapter {
  SimulatedScaleAdapter({
    this.targetGrams = 4800,
    this.tickInterval = const Duration(milliseconds: 400),
  });

  /// The weight the scale settles on, in grams.
  final int targetGrams;
  final Duration tickInterval;

  final StreamController<ScaleReading> _controller = StreamController<ScaleReading>.broadcast();
  Timer? _timer;
  int _tick = 0;
  ScaleState _state = ScaleState.disconnected;

  @override
  ScaleAdapterInfo get info =>
      const ScaleAdapterInfo(key: 'simulated', connection: 'hid', devOnly: true);

  @override
  String? get deviceLabel => 'Simulated scale';

  @override
  Future<void> connect() async {
    _state = ScaleState.connecting;
    _tick = 0;
    await Future<void>.delayed(const Duration(milliseconds: 200));
    _state = ScaleState.connected;
    _timer?.cancel();
    _timer = Timer.periodic(tickInterval, (_) => _emit());
  }

  void _emit() {
    if (_controller.isClosed) return;
    _tick++;
    // First few ticks wobble widely (unstable), then settle within tolerance.
    final int grams;
    if (_tick < 3) {
      grams = targetGrams + (_tick.isEven ? 180 : -140) + _tick * 7;
    } else {
      grams = targetGrams + (_tick.isEven ? 4 : -3);
    }
    _state = ScaleState.reading;
    _controller.add(ScaleReading(grams: grams, timestamp: DateTime.now()));
  }

  /// Simulate the scale dropping off mid-reading (for the "never save a
  /// disconnected value" acceptance test).
  Future<void> simulateDisconnect() async {
    _timer?.cancel();
    _state = ScaleState.disconnected;
  }

  @override
  Future<void> disconnect() async {
    _timer?.cancel();
    _state = ScaleState.disconnected;
  }

  @override
  ScaleState status() => _state;

  @override
  Stream<ScaleReading> stream() => _controller.stream;

  @override
  ScaleReading? parse(List<int> bytes) => null; // simulated readings are pre-parsed

  @override
  Future<void> dispose() async {
    _timer?.cancel();
    await _controller.close();
  }
}
