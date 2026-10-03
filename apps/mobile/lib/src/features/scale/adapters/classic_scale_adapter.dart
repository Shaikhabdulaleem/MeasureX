import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/services.dart';

import '../scale_adapter.dart';
import '../scale_models.dart';
import '../weight_parser.dart';

/// Bluetooth Classic (serial / SPP) scale adapter — Android only (PRD §9:
/// iOS needs MFi certification). The SPP socket lives in a small Kotlin plugin;
/// this Dart side drives it over a MethodChannel and receives raw frames over an
/// EventChannel, then parses them with the shared, pluggable [WeightParser].
///
/// Skeleton: the Kotlin side opens the socket and streams bytes; per-model
/// framing is finished once a concrete model is chosen (PRD Q6).
class ClassicScaleConfig {
  const ClassicScaleConfig({this.deviceAddress, this.parser = const WeightParser()});

  /// MAC address of the paired SPP device; null lets the plugin pick the first
  /// paired scale-class device.
  final String? deviceAddress;
  final WeightParser parser;
}

class ClassicScaleAdapter extends ScaleAdapter {
  ClassicScaleAdapter(this.config);

  final ClassicScaleConfig config;

  static const MethodChannel _method = MethodChannel('measurex/scale_classic');
  static const EventChannel _events = EventChannel('measurex/scale_classic/readings');

  StreamSubscription<dynamic>? _eventSub;
  final StreamController<ScaleReading> _controller = StreamController<ScaleReading>.broadcast();
  ScaleState _state = ScaleState.disconnected;

  @override
  ScaleAdapterInfo get info =>
      const ScaleAdapterInfo(key: 'classic', connection: 'classic', devOnly: false);

  @override
  String? get deviceLabel => config.deviceAddress;

  @override
  ScaleState status() => _state;

  @override
  Stream<ScaleReading> stream() => _controller.stream;

  @override
  Future<void> connect() async {
    if (!Platform.isAndroid) {
      _state = ScaleState.error; // Classic/SPP is Android-only (PRD §9).
      return;
    }
    _state = ScaleState.connecting;
    try {
      await _method.invokeMethod<void>('connect', {'address': config.deviceAddress});
      _eventSub = _events.receiveBroadcastStream().listen(_onEvent, onError: (_) {
        _state = ScaleState.error;
      });
      _state = ScaleState.connected;
    } on PlatformException {
      _state = ScaleState.error;
    }
  }

  void _onEvent(dynamic event) {
    if (_controller.isClosed) return;
    // The plugin forwards raw bytes (List<int>) or a decoded line (String).
    final ScaleReading? reading;
    if (event is List) {
      reading = parse(event.cast<int>());
    } else if (event is String) {
      reading = _fromText(event);
    } else {
      reading = null;
    }
    if (reading != null) {
      _state = ScaleState.reading;
      _controller.add(reading);
    }
  }

  ScaleReading? _fromText(String text) {
    final parsed = config.parser.parse(text);
    if (parsed == null) return null;
    return ScaleReading(
      grams: parsed.grams,
      timestamp: DateTime.now(),
      deviceStable: parsed.deviceStable,
    );
  }

  @override
  ScaleReading? parse(List<int> bytes) => _fromText(String.fromCharCodes(bytes));

  @override
  Future<void> disconnect() async {
    await _eventSub?.cancel();
    _eventSub = null;
    try {
      await _method.invokeMethod<void>('disconnect');
    } on PlatformException {
      // best effort
    }
    _state = ScaleState.disconnected;
  }

  @override
  Future<void> dispose() async {
    await disconnect();
    await _controller.close();
  }
}
