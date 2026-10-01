import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/billing.dart';
import 'capture_controller.dart';
import 'package_saved_screen.dart';
import 'widgets.dart';

/// Review screen — shows the billing PREVIEW computed by the shared Dart port.
/// The server value is final (CLAUDE.md rule 2); this is a preview only.
class ReviewScreen extends ConsumerStatefulWidget {
  const ReviewScreen({
    super.key,
    required this.lengthMm,
    required this.widthMm,
    required this.heightMm,
    required this.photoBytes,
  });

  final int lengthMm;
  final int widthMm;
  final int heightMm;
  final Uint8List photoBytes;

  @override
  ConsumerState<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends ConsumerState<ReviewScreen> {
  bool _saving = false;

  Future<void> _confirm() async {
    final l10n = AppLocalizations.of(context);
    setState(() => _saving = true);
    try {
      final pkg = await ref.read(captureControllerProvider.notifier).savePackage(
            lengthMm: widget.lengthMm,
            widthMm: widget.widthMm,
            heightMm: widget.heightMm,
            photoBytes: widget.photoBytes,
          );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => PackageSavedScreen(packageNumber: pkg.packageNumber ?? 0),
        ),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.genericError)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final cfg = ref.watch(effectiveConfigProvider).valueOrNull;

    final preview = computeBilling(
      lengthMm: widget.lengthMm,
      widthMm: widget.widthMm,
      heightMm: widget.heightMm,
      divisor: cfg?.volumetricDivisor ?? kDefaultDivisor,
      chargeableStepKg: cfg?.chargeableStepKg ?? kDefaultChargeableStepKg,
    );

    return Scaffold(
      appBar: AppBar(title: Text(l10n.review)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.memory(widget.photoBytes, height: 200, fit: BoxFit.cover),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                children: [
                  kvRow(
                    l10n.billingDimensions,
                    '${preview.billingLCm} × ${preview.billingWCm} × ${preview.billingHCm} cm',
                  ),
                  kvRow(l10n.cbm, cbmStr(preview.cbm)),
                  kvRow(l10n.volumetric, kg(preview.volumetricG)),
                  kvRow(l10n.chargeable, kgStep(preview.chargeableG), emphasise: true),
                  const Divider(height: 24),
                  kvRow(l10n.method, l10n.manual),
                ],
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              height: 60,
              child: FilledButton(
                onPressed: _saving ? null : _confirm,
                child: Text(_saving ? l10n.saving : l10n.confirmSave),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
