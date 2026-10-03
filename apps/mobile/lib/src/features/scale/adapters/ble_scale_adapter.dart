import 'dart:async';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../scale_adapter.dart';
import '../scale_models.dart';
import '../weight_parser.dart';

/// Configurable BLE binding for a scale model (PRD §9). The service and
/// characteristic UUIDs and the parser come from the scale's record, so a new
/// BLE model is added as data without touching this adapter.
class BleScaleConfig {
  const BleScaleConfig({
    required this.serviceUuid,
    required this.characteristicUuid,
    this.namePrefix,
    this.parser = const WeightParser(),
  });

  final String serviceUuid;
  final String characteristicUuid;

  /// Optional advertised-name prefix to match the right device while scanning.
  final String? namePrefix;
  final WeightParser parser;
}

/// BLE (GATT) scale adapter skeleton built on `flutter_blue_plus` (PRD §9):
/// scan → connect → discover → subscribe to the configured notify
/// characteristic → parse each frame with the pluggable [WeightParser].
///
/// Real-device behaviour (bonding quirks, reconnection, per-model framing) is
/// finished once a concrete model is chosen (PRD Q6); the structure and the
/// parser plug-in are in place so that is a data/config change.
class BleScaleAdapter extends ScaleAdapter {
  BleScaleAdapter(this.config);

  final BleScaleConfig config;

  BluetoothDevice? _device;
  StreamSubscription<List<int>>? _valueSub;
  StreamSubscription<List<ScanResult>>? _scanSub;
  final StreamController<ScaleReading> _controller = StreamController<ScaleReading>.broadcast();
  ScaleState _state = ScaleState.disconnected;

  @override
  ScaleAdapterInfo get info =>
      const ScaleAdapterInfo(key: 'ble', connection: 'ble', devOnly: false);

  @override
  String? get deviceLabel => _device?.platformName;

  @override
  ScaleState status() => _state;

  @override
  Stream<ScaleReading> stream() => _controller.stream;

  @override
  Future<void> connect() async {
    _state = ScaleState.connecting;
    try {
      final device = await _scanForDevice();
      if (device == null) {
        _state = ScaleState.error;
        return;
      }
      _device = device;
      await device.connect();
      await _subscribe(device);
      _state = ScaleState.connected;
    } catch (_) {
      _state = ScaleState.error;
    }
  }

  Future<BluetoothDevice?> _scanForDevice() async {
    final completer = Completer<BluetoothDevice?>();
    final serviceGuid = Guid(config.serviceUuid);

    _scanSub = FlutterBluePlus.scanResults.listen((results) {
      for (final r in results) {
        final nameOk = config.namePrefix == null ||
            r.device.platformName.startsWith(config.namePrefix!);
        if (nameOk && !completer.isCompleted) {
          completer.complete(r.device);
        }
      }
    });

    await FlutterBluePlus.startScan(
      withServices: [serviceGuid],
      timeout: const Duration(seconds: 10),
    );
    final device = await completer.future
        .timeout(const Duration(seconds: 12), onTimeout: () => null);
    await FlutterBluePlus.stopScan();
    await _scanSub?.cancel();
    _scanSub = null;
    return device;
  }

  Future<void> _subscribe(BluetoothDevice device) async {
    final services = await device.discoverServices();
    final serviceGuid = Guid(config.serviceUuid);
    final charGuid = Guid(config.characteristicUuid);
    for (final service in services) {
      if (service.uuid != serviceGuid) continue;
      for (final characteristic in service.characteristics) {
        if (characteristic.uuid != charGuid) continue;
        await characteristic.setNotifyValue(true);
        _valueSub = characteristic.lastValueStream.listen(_onValue);
        return;
      }
    }
    throw StateError('Configured BLE characteristic not found');
  }

  void _onValue(List<int> bytes) {
    final reading = parse(bytes);
    if (reading != null && !_controller.isClosed) {
      _state = ScaleState.reading;
      _controller.add(reading);
    }
  }

  @override
  ScaleReading? parse(List<int> bytes) {
    final parsed = config.parser.parse(String.fromCharCodes(bytes));
    if (parsed == null) return null;
    return ScaleReading(
      grams: parsed.grams,
      timestamp: DateTime.now(),
      deviceStable: parsed.deviceStable,
    );
  }

  @override
  Future<void> disconnect() async {
    await _valueSub?.cancel();
    _valueSub = null;
    await _scanSub?.cancel();
    _scanSub = null;
    try {
      await _device?.disconnect();
    } catch (_) {
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
