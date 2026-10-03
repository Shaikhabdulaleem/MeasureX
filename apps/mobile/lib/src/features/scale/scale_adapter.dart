import 'scale_models.dart';
import 'weight_parser.dart';

/// Metadata describing an adapter so Settings can list the choices (PRD §9).
class ScaleAdapterInfo {
  const ScaleAdapterInfo({
    required this.key,
    required this.connection,
    required this.devOnly,
  });

  /// Matches the server `Scale.adapterKey` (e.g. "simulated", "hid", "ble", "classic").
  final String key;

  /// "ble", "classic" or "hid" (PRD §9 connection types).
  final String connection;

  /// Simulated adapter is available in dev/debug builds only.
  final bool devOnly;
}

/// One scale behind one interface (PRD §9). Concrete adapters (simulated, HID,
/// BLE, Bluetooth Classic) implement this; the capture flow and controller only
/// ever talk to this interface, so a new model is added without touching them.
abstract class ScaleAdapter {
  ScaleAdapterInfo get info;

  /// A human label for the connected device (e.g. the scale model), if known.
  String? get deviceLabel;

  /// Connect to (or begin connecting to) the scale.
  Future<void> connect();

  /// Disconnect and release resources.
  Future<void> disconnect();

  /// The current coarse connection state.
  ScaleState status();

  /// A stream of raw readings. Parsing happens via [parse]; adapters that
  /// receive text frames use the shared [WeightParser].
  Stream<ScaleReading> stream();

  /// Parse a raw frame into a reading. Adapters delegate to a pluggable parser;
  /// exposed so it can be unit-tested per model.
  ScaleReading? parse(List<int> bytes);

  /// Zero the scale, when the model supports it. No-op otherwise.
  Future<void> tare() async {}

  /// Release streams/connections permanently.
  Future<void> dispose() async {}
}
