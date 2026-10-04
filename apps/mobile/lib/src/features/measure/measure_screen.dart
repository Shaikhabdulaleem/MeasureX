import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import '../capture/manual_dimensions_screen.dart';
import 'measurement_engine.dart';

/// Phase B / B1 camera measurement (PRD §4). Streams camera frames to the
/// C++/OpenCV engine over FFI, shows the live marker count + a first-cut L×W
/// estimate + a confidence chip, and hands the measured L/W to the manual
/// screen (prefilled, method = marker) so the worker confirms height and saves.
///
/// B1 is a feasibility slice: height is not yet measured (needs camera pose, B2)
/// and metric accuracy is validated separately against a tape (the B1 gate).
class MeasureScreen extends ConsumerStatefulWidget {
  const MeasureScreen({super.key});

  @override
  ConsumerState<MeasureScreen> createState() => _MeasureScreenState();
}

/// PRD §4 confidence over a short window of frames.
enum _Conf { low, medium, high }

class _MeasureScreenState extends ConsumerState<MeasureScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  bool _initError = false;
  bool _busy = false; // a frame is being processed
  DateTime _lastRun = DateTime.fromMillisecondsSinceEpoch(0);

  // Rolling window of recent OK samples for median + spread (PRD §4).
  final List<MeasurementSample> _window = [];
  int _markerCount = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      final back = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        back,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await controller.initialize();
      if (!mounted) return;
      await controller.startImageStream(_onFrame);
      setState(() => _controller = controller);
    } catch (_) {
      if (mounted) setState(() => _initError = true);
    }
  }

  void _onFrame(CameraImage image) {
    // Throttle to ~4 fps and never overlap work.
    final now = DateTime.now();
    if (_busy || now.difference(_lastRun).inMilliseconds < 250) return;
    _busy = true;
    _lastRun = now;
    try {
      final engine = ref.read(measurementEngineProvider);
      if (!engine.available) {
        _busy = false;
        return;
      }
      // Downscale the Y (luma) plane by 2 for speed; scale is self-consistent
      // because the engine derives mm/px from markers in the same image.
      final gray = _packLumaHalf(image);
      final w = image.width ~/ 2;
      final h = image.height ~/ 2;
      final sample = engine.measureGray(gray, w, h);
      if (!mounted) return;
      setState(() {
        _markerCount = sample.markerCount;
        if (sample.ok) {
          _window.add(sample);
          if (_window.length > 8) _window.removeAt(0);
        }
      });
    } finally {
      _busy = false;
    }
  }

  /// Pack the Y plane into a dense (width/2 x height/2) grayscale buffer,
  /// honouring the plane's row stride (which is often padded).
  static Uint8List _packLumaHalf(CameraImage image) {
    final plane = image.planes[0];
    final rowStride = plane.bytesPerRow;
    final src = plane.bytes;
    final w = image.width ~/ 2;
    final h = image.height ~/ 2;
    final out = Uint8List(w * h);
    var o = 0;
    for (var y = 0; y < h; y++) {
      final rowBase = (y * 2) * rowStride;
      for (var x = 0; x < w; x++) {
        out[o++] = src[rowBase + x * 2];
      }
    }
    return out;
  }

  // Median L/W over the window and the confidence level (PRD §4).
  (int, int, _Conf) _aggregate() {
    if (_window.isEmpty) return (0, 0, _Conf.low);
    final lengths = _window.map((s) => s.lengthMm).toList()..sort();
    final widths = _window.map((s) => s.widthMm).toList()..sort();
    final medL = lengths[lengths.length ~/ 2];
    final medW = widths[widths.length ~/ 2];
    final spread = (lengths.last - lengths.first).abs();
    _Conf conf;
    if (_markerCount >= 4 && spread <= 10) {
      conf = _Conf.high;
    } else if (_markerCount >= 2 && spread <= 25) {
      conf = _Conf.medium;
    } else {
      conf = _Conf.low;
    }
    return (medL, medW, conf);
  }

  Future<void> _use(int lengthMm, int widthMm, _Conf conf) async {
    await _controller?.stopImageStream().catchError((_) {});
    if (!mounted) return;
    final confidence = switch (conf) {
      _Conf.high => 'high',
      _Conf.medium => 'medium',
      _Conf.low => 'low',
    };
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => ManualDimensionsScreen(
          initialLengthMm: lengthMm,
          initialWidthMm: widthMm,
          method: 'marker',
          confidence: confidence,
        ),
      ),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final c = _controller;
    if (c == null || !c.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      c.dispose();
      _controller = null;
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final engine = ref.read(measurementEngineProvider);
    final controller = _controller;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.measureWithCamera)),
      body: !engine.available
          ? _centered(l10n.measureEngineUnavailable)
          : _initError
              ? _centered(l10n.genericError)
              : controller == null || !controller.value.isInitialized
                  ? const Center(child: CircularProgressIndicator())
                  : _liveView(context, l10n, controller),
    );
  }

  Widget _liveView(BuildContext context, AppLocalizations l10n,
      CameraController controller) {
    final (medL, medW, conf) = _aggregate();
    final hasMeasure = medL > 0 && medW > 0;
    final (confLabel, confColor) = switch (conf) {
      _Conf.high => (l10n.confidenceHigh, Colors.green),
      _Conf.medium => (l10n.confidenceMedium, Colors.orange),
      _Conf.low => (l10n.confidenceLow, Colors.red),
    };
    final guidance = _markerCount < 2
        ? l10n.showMoreMarkers
        : (!hasMeasure
            ? l10n.placeBoxOnMat
            : '${l10n.markersDetected}: $_markerCount');

    return Column(
      children: [
        Expanded(child: CameraPreview(controller)),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          color: Theme.of(context).colorScheme.surface,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Chip(
                    avatar: Icon(Icons.qr_code, size: 18, color: confColor),
                    label: Text('${l10n.markersDetected}: $_markerCount'),
                  ),
                  const SizedBox(width: 8),
                  Chip(
                    backgroundColor: confColor.withValues(alpha: 0.15),
                    label: Text(confLabel, style: TextStyle(color: confColor)),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                hasMeasure
                    ? '${l10n.length}: ${(medL / 10).toStringAsFixed(1)} cm   ·   '
                        '${l10n.width}: ${(medW / 10).toStringAsFixed(1)} cm'
                    : guidance,
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              Text(l10n.heightEnteredManually,
                  style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: hasMeasure ? () => _use(medL, medW, conf) : null,
                icon: const Icon(Icons.check),
                label: Text(l10n.useMeasurement),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _centered(String text) => Padding(
        padding: const EdgeInsets.all(24),
        child: Center(child: Text(text, textAlign: TextAlign.center)),
      );
}
