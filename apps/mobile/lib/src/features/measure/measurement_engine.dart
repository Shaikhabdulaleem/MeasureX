import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Result of measuring one camera frame with the C++/OpenCV core (PRD §4, B1).
class MeasurementSample {
  const MeasurementSample({
    required this.ok,
    required this.markerCount,
    required this.lengthMm,
    required this.widthMm,
    required this.heightMm,
    required this.mmPerPx,
  });

  /// True when a box base rectangle was measured this frame.
  final bool ok;
  final int markerCount;
  final int lengthMm;
  final int widthMm;
  final int heightMm;
  final double mmPerPx;

  static const empty = MeasurementSample(
      ok: false,
      markerCount: 0,
      lengthMm: 0,
      widthMm: 0,
      heightMm: 0,
      mmPerPx: 0);
}

/// The PRD's `MeasurementEngine` seam: one grayscale frame in → a sample out.
/// Phase C AR will provide a different implementation behind this same seam.
abstract class MeasurementEngine {
  /// Measure an 8-bit grayscale frame ([gray] is `width*height` bytes,
  /// row-major, no padding). [markerSizeMm] is the printed marker side length.
  MeasurementSample measureGray(Uint8List gray, int width, int height,
      {int markerSizeMm = 100});

  /// A human-readable engine/version string (for diagnostics).
  String version();

  /// True when a real native engine is loaded (false for the no-op fallback).
  bool get available;
}

/// Fallback used where the native library is absent (desktop, CI, tests) so the
/// app still runs and `flutter analyze`/`flutter test` pass without the `.so`.
class NoopMeasurementEngine implements MeasurementEngine {
  @override
  MeasurementSample measureGray(Uint8List gray, int width, int height,
          {int markerSizeMm = 100}) =>
      MeasurementSample.empty;

  @override
  String version() => 'measurex (native engine unavailable)';

  @override
  bool get available => false;
}

// --- FFI bindings to libmeasurex.so ----------------------------------------

final class _MxParams extends Struct {
  @Int32()
  external int markerSizeMm;
  @Int32()
  external int zoneMarginPx;
  @Int32()
  external int minContourAreaPx;
}

// Field order MUST match include/measurex/measure.h MxResult exactly.
final class _MxResult extends Struct {
  @Int32()
  external int ok;
  @Int32()
  external int markerCount;
  @Int32()
  external int lengthMm;
  @Int32()
  external int widthMm;
  @Int32()
  external int heightMm;
  @Double()
  external double mmPerPx;
  @Int32()
  external int confidence;
}

typedef _MeasureNative = Int32 Function(
    Pointer<Uint8>, Int32, Int32, Pointer<_MxParams>, Pointer<_MxResult>);
typedef _MeasureDart = int Function(
    Pointer<Uint8>, int, int, Pointer<_MxParams>, Pointer<_MxResult>);
typedef _VersionNative = Pointer<Utf8> Function();

/// FFI engine backed by the C ABI in `packages/measure-core` (OpenCV ArUco).
class FfiMeasurementEngine implements MeasurementEngine {
  FfiMeasurementEngine._(this._lib, this._measure, this._version);

  // Retained so the loaded library stays alive for the app's lifetime.
  // ignore: unused_field
  final DynamicLibrary _lib;
  final _MeasureDart _measure;
  final _VersionNative _version;

  @override
  bool get available => true;

  /// Load `libmeasurex.so`; returns null if it cannot be opened (so the caller
  /// can fall back to the no-op engine).
  static FfiMeasurementEngine? tryLoad() {
    try {
      // Android/Linux link the symbols into libmeasurex.so.
      final lib = Platform.isAndroid || Platform.isLinux
          ? DynamicLibrary.open('libmeasurex.so')
          : DynamicLibrary.process();
      final measure = lib.lookupFunction<_MeasureNative, _MeasureDart>(
          'measurex_measure_frame');
      final version = lib
          .lookupFunction<_VersionNative, _VersionNative>('measurex_version');
      return FfiMeasurementEngine._(lib, measure, version);
    } catch (_) {
      return null;
    }
  }

  @override
  MeasurementSample measureGray(Uint8List gray, int width, int height,
      {int markerSizeMm = 100}) {
    final Pointer<Uint8> buf = malloc<Uint8>(gray.length);
    final Pointer<_MxParams> params = malloc<_MxParams>();
    final Pointer<_MxResult> out = malloc<_MxResult>();
    try {
      buf.asTypedList(gray.length).setAll(0, gray);
      params.ref
        ..markerSizeMm = markerSizeMm
        ..zoneMarginPx = 0
        ..minContourAreaPx = 1500;
      final rc = _measure(buf, width, height, params, out);
      if (rc != 0) return MeasurementSample.empty;
      final r = out.ref;
      return MeasurementSample(
        ok: r.ok == 1,
        markerCount: r.markerCount,
        lengthMm: r.lengthMm,
        widthMm: r.widthMm,
        heightMm: r.heightMm,
        mmPerPx: r.mmPerPx,
      );
    } finally {
      malloc.free(buf);
      malloc.free(params);
      malloc.free(out);
    }
  }

  @override
  String version() {
    try {
      return _version().toDartString();
    } catch (_) {
      return 'measurex (version unavailable)';
    }
  }
}

/// App-wide engine: the FFI engine when the native lib is present, else no-op.
final measurementEngineProvider = Provider<MeasurementEngine>((ref) {
  return FfiMeasurementEngine.tryLoad() ?? NoopMeasurementEngine();
});
