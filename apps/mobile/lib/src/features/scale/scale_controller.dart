import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import 'adapters/ble_scale_adapter.dart';
import 'adapters/classic_scale_adapter.dart';
import 'adapters/hid_keyboard_scale_adapter.dart';
import 'adapters/simulated_scale_adapter.dart';
import 'scale_adapter.dart';
import 'scale_models.dart';
import 'scale_store.dart';
import 'stability_detector.dart';

/// Live scale state exposed to the UI. [grams] is the current value; it is only
/// safe to SAVE when [canCapture] is true (connected + stable + fresh, PRD §9).
@immutable
class ScaleRuntime {
  const ScaleRuntime({
    this.state = ScaleState.disconnected,
    this.grams,
    this.stable = false,
    this.stale = false,
    this.scale,
    this.deviceLabel,
  });

  final ScaleState state;
  final int? grams;
  final bool stable;
  final bool stale;

  /// The selected approved scale (model + thresholds), when one is chosen.
  final ScaleModel? scale;
  final String? deviceLabel;

  bool get isConnected =>
      state != ScaleState.disconnected && state != ScaleState.error;

  /// A value may be captured only from a connected, stable, non-stale reading
  /// (PRD §9 — never save an unstable, stale or disconnected value).
  bool get canCapture => isConnected && stable && !stale && grams != null;

  ScaleRuntime copyWith({
    ScaleState? state,
    int? grams,
    bool? stable,
    bool? stale,
    ScaleModel? scale,
    String? deviceLabel,
    bool clearGrams = false,
    bool clearScale = false,
  }) {
    return ScaleRuntime(
      state: state ?? this.state,
      grams: clearGrams ? null : (grams ?? this.grams),
      stable: stable ?? this.stable,
      stale: stale ?? this.stale,
      scale: clearScale ? null : (scale ?? this.scale),
      deviceLabel: deviceLabel ?? this.deviceLabel,
    );
  }
}

final scaleStoreProvider = Provider<ScaleStore>((ref) => ScaleStore());

final scaleControllerProvider =
    StateNotifierProvider<ScaleController, ScaleRuntime>((ref) {
  return ScaleController(ref);
});

class ScaleController extends StateNotifier<ScaleRuntime> {
  ScaleController(this._ref) : super(const ScaleRuntime());

  final Ref _ref;

  ScaleAdapter? _adapter;
  StabilityDetector? _detector;
  StreamSubscription<ScaleReading>? _sub;
  Timer? _stalenessTimer;

  ApiClient get _api => _ref.read(apiClientProvider);
  String? get _token => _ref.read(authControllerProvider).accessToken;

  /// Load approved scales and, if one was remembered, reconnect to it (PRD §9).
  Future<List<ScaleModel>> loadScales() async {
    final token = _token;
    if (token == null) return const [];
    final scales = await _api.listScales(token);
    final rememberedId = await _ref.read(scaleStoreProvider).readScaleId();
    if (rememberedId != null && state.scale == null) {
      final match = scales.where((s) => s.id == rememberedId).toList();
      if (match.isNotEmpty) {
        await select(match.first, remember: false);
        await connect();
      }
    }
    return scales;
  }

  /// Choose a scale (builds its adapter + detector). Does not connect.
  Future<void> select(ScaleModel scale, {bool remember = true}) async {
    await _teardown();
    _adapter = _buildAdapter(scale);
    _detector = StabilityDetector(ScaleThresholds(
      window: scale.stabilityWindow,
      toleranceG: scale.stabilityToleranceG,
      windowMs: scale.stabilityWindowMs,
      minWeightG: scale.minWeightG,
      staleAfterMs: scale.staleAfterMs,
      streaming: scale.streaming,
    ));
    state = ScaleRuntime(scale: scale, state: ScaleState.disconnected);
    if (remember) {
      await _ref.read(scaleStoreProvider).saveScaleId(scale.id);
    }
  }

  ScaleAdapter _buildAdapter(ScaleModel scale) {
    switch (scale.adapterKey) {
      case 'simulated':
        return SimulatedScaleAdapter();
      case 'ble':
        return BleScaleAdapter(const BleScaleConfig(
          // Placeholder UUIDs until a concrete model is chosen (PRD Q6); these
          // come from the scale record once the model is known.
          serviceUuid: '0000ffe0-0000-1000-8000-00805f9b34fb',
          characteristicUuid: '0000ffe1-0000-1000-8000-00805f9b34fb',
        ));
      case 'classic':
        return ClassicScaleAdapter(const ClassicScaleConfig());
      case 'hid':
      default:
        return HidKeyboardScaleAdapter();
    }
  }

  /// The HID adapter when one is selected (the capture screen pumps typed lines
  /// into it); null for every other adapter.
  HidKeyboardScaleAdapter? get hidAdapter =>
      _adapter is HidKeyboardScaleAdapter ? _adapter as HidKeyboardScaleAdapter : null;

  /// Simulated adapter (dev/test builds), for the "settle then disconnect" demo.
  SimulatedScaleAdapter? get simulatedAdapter =>
      _adapter is SimulatedScaleAdapter ? _adapter as SimulatedScaleAdapter : null;

  Future<void> connect() async {
    final adapter = _adapter;
    final detector = _detector;
    if (adapter == null || detector == null) return;

    detector.reset();
    state = state.copyWith(state: ScaleState.connecting, clearGrams: true, stable: false, stale: false);
    await _sub?.cancel();
    _sub = adapter.stream().listen(_onReading, onError: (_) {
      state = state.copyWith(state: ScaleState.error, stable: false);
    });

    await adapter.connect();
    final s = adapter.status();
    state = state.copyWith(state: s, deviceLabel: adapter.deviceLabel);

    // Watchdog: if readings stop, flip a stable value to stale and reflect the
    // adapter dropping the connection (PRD §9 — never keep a stale value).
    _stalenessTimer?.cancel();
    _stalenessTimer = Timer.periodic(const Duration(seconds: 1), (_) => _checkStaleness());
  }

  void _onReading(ScaleReading reading) {
    final detector = _detector;
    final adapter = _adapter;
    if (detector == null || adapter == null) return;
    // If the adapter has dropped, ignore late readings entirely.
    if (adapter.status() == ScaleState.disconnected) return;

    final result = detector.add(reading, now: DateTime.now());
    state = state.copyWith(
      state: result.phase,
      grams: result.grams,
      stable: result.stable,
      stale: result.stale,
      // A below-min reading clears the value (nothing on the scale, PRD §9).
      clearGrams: result.grams == null,
    );
  }

  void _checkStaleness() {
    final detector = _detector;
    final adapter = _adapter;
    if (detector == null || adapter == null) return;

    final adapterState = adapter.status();
    if (adapterState == ScaleState.disconnected || adapterState == ScaleState.error) {
      // Connection gone → drop any value immediately (never save it).
      state = state.copyWith(
        state: adapterState,
        stable: false,
        stale: false,
        clearGrams: true,
      );
      return;
    }

    final result = detector.evaluate(DateTime.now());
    if (result.stale) {
      state = state.copyWith(state: ScaleState.reading, stable: false, stale: true, clearGrams: true);
    }
  }

  Future<void> tare() async => _adapter?.tare();

  Future<void> disconnect() async {
    _stalenessTimer?.cancel();
    _stalenessTimer = null;
    await _sub?.cancel();
    _sub = null;
    await _adapter?.disconnect();
    _detector?.reset();
    state = state.copyWith(
      state: ScaleState.disconnected,
      stable: false,
      stale: false,
      clearGrams: true,
    );
  }

  Future<void> _teardown() async {
    _stalenessTimer?.cancel();
    _stalenessTimer = null;
    await _sub?.cancel();
    _sub = null;
    await _adapter?.dispose();
    _adapter = null;
    _detector = null;
  }

  /// Whether the simulated adapter is offered (dev/debug builds only).
  static bool get simulatedAvailable => kDebugMode;

  @override
  void dispose() {
    _stalenessTimer?.cancel();
    _sub?.cancel();
    _adapter?.dispose();
    super.dispose();
  }
}
