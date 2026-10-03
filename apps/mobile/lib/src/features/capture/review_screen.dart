import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/billing.dart';
import '../auth/auth_controller.dart';
import '../scale/scale_controller.dart';
import '../scale/scale_ui.dart';
import 'capture_controller.dart';
import 'package_saved_screen.dart';
import 'widgets.dart';

/// Review screen — shows the billing PREVIEW computed by the shared Dart port.
/// The server value is final (CLAUDE.md rule 2); this is a preview only.
///
/// Weight (PRD §9) is captured in parallel: a stable scale reading is picked up
/// automatically; a Team Leader may enter it manually (reason required). An
/// unstable, stale or disconnected reading is never used.
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

/// The weight the user will save, with its provenance.
class _ChosenWeight {
  const _ChosenWeight({required this.grams, required this.source, this.scaleId, this.reason, this.label});
  final int grams;
  final String source; // 'scale' | 'manual'
  final String? scaleId;
  final String? reason;
  final String? label;
}

class _ReviewScreenState extends ConsumerState<ReviewScreen> {
  bool _saving = false;
  _ChosenWeight? _manualWeight;

  /// The effective weight to save: a manual entry wins when present, else a
  /// stable scale reading. Null when neither is available (PRD §9).
  _ChosenWeight? _effectiveWeight(ScaleRuntime scale, AppLocalizations l10n) {
    if (_manualWeight != null) return _manualWeight;
    if (scale.canCapture && scale.grams != null) {
      final model = scale.scale?.model;
      return _ChosenWeight(
        grams: scale.grams!,
        source: 'scale',
        scaleId: scale.scale?.id,
        label: model == null ? l10n.stable : '$model · ${l10n.stable}',
      );
    }
    return null;
  }

  Future<void> _confirm(_ChosenWeight? weight) async {
    final l10n = AppLocalizations.of(context);
    setState(() => _saving = true);
    try {
      final pkg = await ref.read(captureControllerProvider.notifier).savePackage(
            lengthMm: widget.lengthMm,
            widthMm: widget.widthMm,
            heightMm: widget.heightMm,
            photoBytes: widget.photoBytes,
            weightSource: weight?.source ?? 'none',
            actualWeightG: weight?.grams,
            scaleId: weight?.scaleId,
            weightReason: weight?.reason,
          );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => PackageSavedScreen(
            displayNumber: pkg.serverNumber ?? pkg.provisionalNumber,
            provisional: pkg.serverNumber == null,
          ),
        ),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.genericError)));
    }
  }

  Future<void> _enterManualWeight() async {
    final result = await showDialog<_ChosenWeight>(
      context: context,
      builder: (_) => const _ManualWeightDialog(),
    );
    if (!mounted) return;
    if (result != null) setState(() => _manualWeight = result);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final cfg = ref.watch(effectiveConfigProvider).valueOrNull;
    final scale = ref.watch(scaleControllerProvider);
    final role = ref.watch(authControllerProvider).user?.role;
    final canManualWeight = role == 'team_leader' || role == 'admin';

    final preview = computeBilling(
      lengthMm: widget.lengthMm,
      widthMm: widget.widthMm,
      heightMm: widget.heightMm,
      divisor: cfg?.volumetricDivisor ?? kDefaultDivisor,
      chargeableStepKg: cfg?.chargeableStepKg ?? kDefaultChargeableStepKg,
    );

    final weight = _effectiveWeight(scale, l10n);
    final weightRequired = cfg?.weightRequired ?? true;
    final blocked = weightRequired && weight == null;

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
            const SizedBox(height: 12),
            // Live scale status — weight is captured automatically when stable.
            const ScaleStatusChip(showWeight: true),
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
                  kvRow(
                    l10n.weight,
                    weight == null ? '—' : '${kg(weight.grams)}  (${weight.label ?? _sourceText(l10n, weight.source)})',
                  ),
                ],
              ),
            ),
            if (blocked)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  l10n.waitingForStableWeight,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (canManualWeight)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: TextButton.icon(
                  onPressed: _enterManualWeight,
                  icon: const Icon(Icons.edit),
                  label: Text(l10n.enterManualWeight),
                ),
              ),
            const SizedBox(height: 16),
            SizedBox(
              height: 60,
              child: FilledButton(
                onPressed: (_saving || blocked) ? null : () => _confirm(weight),
                child: Text(_saving ? l10n.saving : l10n.confirmSave),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _sourceText(AppLocalizations l10n, String source) =>
      source == 'manual' ? l10n.manualWeight : l10n.scaleStatus;
}

/// Team Leader / Admin manual weight entry: value + mandatory reason (PRD §9).
class _ManualWeightDialog extends StatefulWidget {
  const _ManualWeightDialog();

  @override
  State<_ManualWeightDialog> createState() => _ManualWeightDialogState();
}

class _ManualWeightDialogState extends State<_ManualWeightDialog> {
  final _formKey = GlobalKey<FormState>();
  final _weight = TextEditingController();
  final _reason = TextEditingController();

  @override
  void dispose() {
    _weight.dispose();
    _reason.dispose();
    super.dispose();
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final kgValue = double.parse(_weight.text.trim().replaceAll(',', '.'));
    Navigator.of(context).pop(_ChosenWeight(
      grams: (kgValue * 1000).round(),
      source: 'manual',
      reason: _reason.text.trim(),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return AlertDialog(
      title: Text(l10n.manualWeight),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: _weight,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
              decoration: InputDecoration(labelText: l10n.weightKg),
              validator: (v) {
                final parsed = double.tryParse((v ?? '').trim().replaceAll(',', '.'));
                if (parsed == null || parsed <= 0) return l10n.weightKg;
                return null;
              },
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _reason,
              decoration: InputDecoration(labelText: l10n.manualWeightReason),
              validator: (v) => (v == null || v.trim().isEmpty) ? l10n.reasonRequired : null,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: Text(l10n.cancel)),
        FilledButton(onPressed: _submit, child: Text(l10n.save)),
      ],
    );
  }
}
