import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../../core/connectivity.dart';
import '../sync/offline_banner.dart';
import '../sync/sync_providers.dart';
import 'capture_controller.dart';
import '../measure/capture_method_screen.dart';
import 'previous_result_sheet.dart';

/// AWB scanner (Code128 + QR). Accepts only values matching the configured AWB
/// regex; other barcodes are ignored silently (PRD §6). Beeps + vibrates and
/// continues automatically on a match.
class ScannerScreen extends ConsumerStatefulWidget {
  const ScannerScreen({super.key});

  @override
  ConsumerState<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends ConsumerState<ScannerScreen> {
  final MobileScannerController _controller = MobileScannerController(
    formats: const [BarcodeFormat.code128, BarcodeFormat.qrCode],
  );
  bool _handling = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  RegExp _awbRegex() {
    final cfg = ref.read(effectiveConfigProvider).valueOrNull;
    try {
      return RegExp(cfg?.awbRegex ?? r'^AY\d{11}$');
    } catch (_) {
      return RegExp(r'^AY\d{11}$');
    }
  }

  String _normalise(String raw) =>
      raw.replaceAll(RegExp(r'\s+'), '').toUpperCase();

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handling) return;
    final regex = _awbRegex();
    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue;
      if (value == null) continue;
      final awb = _normalise(value);
      if (regex.hasMatch(awb)) {
        _handling = true;
        await _controller.stop();
        unawaited(HapticFeedback.mediumImpact());
        unawaited(SystemSound.play(SystemSoundType.click));
        await _handleAwb(awb);
        return;
      }
      // Non-AWB barcode: ignored silently.
    }
  }

  Future<void> _handleAwb(String awb) async {
    final l10n = AppLocalizations.of(context);

    // Offline: the cross-device history check needs connection (PRD §10). Skip
    // it, warn that previous measurements can't be verified, and continue with
    // a local provisional number.
    final online = ref.read(onlineProvider).valueOrNull ?? true;
    if (!online) {
      await _offlineContinue(awb);
      return;
    }

    try {
      final result =
          await ref.read(captureControllerProvider.notifier).lookup(awb);
      if (!mounted) return;

      if (result.found && result.shipment?.status == 'completed') {
        await showPreviousResultSheet(context, ref, result.shipment!);
        await _resume();
        return;
      }

      ref.read(captureControllerProvider.notifier).startSession(
            awb,
            result.nextPackageNumber,
            shipmentId: result.shipment?.id,
          );
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const CaptureMethodScreen()),
      );
      await _resume();
    } on ApiException catch (e) {
      if (e.code == 'INVALID_AWB') {
        _showError(l10n.invalidAwbFormat);
        await _resume();
      } else {
        // A reachable server returned an error other than bad AWB — treat the
        // lookup as unavailable and continue offline-style.
        await _offlineContinue(awb);
      }
    } catch (_) {
      // Network error → effectively offline; continue with a local number.
      await _offlineContinue(awb);
    }
  }

  /// Continue capture without the cross-device check (offline / lookup down).
  Future<void> _offlineContinue(String awb) async {
    final next = await ref.read(appDatabaseProvider).nextProvisionalNumber(awb);
    ref.read(captureControllerProvider.notifier).startSession(awb, next);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text(kOfflineCannotVerify)),
    );
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const CaptureMethodScreen()),
    );
    await _resume();
  }

  Future<void> _resume() async {
    _handling = false;
    if (mounted) await _controller.start();
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _enterManually() async {
    final l10n = AppLocalizations.of(context);
    final controller = TextEditingController();
    final regex = _awbRegex();
    final awb = await showDialog<String>(
      context: context,
      builder: (ctx) {
        String? error;
        return StatefulBuilder(
          builder: (ctx, setLocal) => AlertDialog(
            title: Text(l10n.enterManually),
            content: TextField(
              controller: controller,
              autofocus: true,
              textCapitalization: TextCapitalization.characters,
              decoration:
                  InputDecoration(labelText: l10n.awb, errorText: error),
              onSubmitted: (_) => Navigator.of(ctx).pop(controller.text),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: Text(l10n.cancel),
              ),
              FilledButton(
                onPressed: () {
                  final value = _normalise(controller.text);
                  if (!regex.hasMatch(value)) {
                    setLocal(() => error = l10n.invalidAwbFormat);
                    return;
                  }
                  Navigator.of(ctx).pop(value);
                },
                child: Text(l10n.continueLabel),
              ),
            ],
          ),
        );
      },
    );
    if (awb != null && mounted) {
      _handling = true;
      await _controller.stop();
      await _handleAwb(awb);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.scanAwb),
        actions: [
          IconButton(
            tooltip: l10n.torch,
            icon: const Icon(Icons.flashlight_on),
            onPressed: () => _controller.toggleTorch(),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              alignment: Alignment.center,
              children: [
                MobileScanner(controller: _controller, onDetect: _onDetect),
                // Simple reticle to guide placement.
                Container(
                  width: 260,
                  height: 160,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white, width: 3),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text(l10n.scanInstruction, textAlign: TextAlign.center),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: OutlinedButton.icon(
                    onPressed: _enterManually,
                    icon: const Icon(Icons.keyboard),
                    label: Text(l10n.enterManually),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
