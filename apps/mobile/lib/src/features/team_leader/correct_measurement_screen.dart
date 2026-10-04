import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import '../capture/widgets.dart';

/// Correct a measurement (PRD §8, §11): original values beside new values, with
/// a mandatory reason. Saving appends a new version via the same API the web
/// uses; the old version is preserved. Pops `true` when a correction was saved.
class CorrectMeasurementScreen extends ConsumerStatefulWidget {
  const CorrectMeasurementScreen({super.key, required this.package});
  final PackageModel package;

  @override
  ConsumerState<CorrectMeasurementScreen> createState() =>
      _CorrectMeasurementScreenState();
}

class _CorrectMeasurementScreenState
    extends ConsumerState<CorrectMeasurementScreen> {
  late final TextEditingController _length;
  late final TextEditingController _width;
  late final TextEditingController _height;
  final _reason = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final v = widget.package.currentVersion;
    _length = TextEditingController(text: v?.lengthMm.toString() ?? '');
    _width = TextEditingController(text: v?.widthMm.toString() ?? '');
    _height = TextEditingController(text: v?.heightMm.toString() ?? '');
  }

  @override
  void dispose() {
    _length.dispose();
    _width.dispose();
    _height.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final l10n = AppLocalizations.of(context);
    final length = int.tryParse(_length.text.trim());
    final width = int.tryParse(_width.text.trim());
    final height = int.tryParse(_height.text.trim());
    final reason = _reason.text.trim();
    if (length == null || width == null || height == null) {
      setState(() => _error = l10n.genericError);
      return;
    }
    if (reason.isEmpty) {
      setState(() => _error = l10n.reasonRequired);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = ref.read(authControllerProvider);
    try {
      await ref.read(apiClientProvider).correctPackage(
            auth.accessToken!,
            widget.package.id,
            lengthMm: length,
            widthMm: width,
            heightMm: height,
            reason: reason,
          );
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.correctionSaved)));
      Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = l10n.actionFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final v = widget.package.currentVersion;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.correctMeasurement)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(pkgLabel(l10n, widget.package.packageNumber ?? 0),
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.original,
                      style: Theme.of(context).textTheme.labelLarge),
                  const SizedBox(height: 8),
                  kvRow(l10n.lengthMm, v?.lengthMm.toString() ?? '—'),
                  kvRow(l10n.widthMm, v?.widthMm.toString() ?? '—'),
                  kvRow(l10n.heightMm, v?.heightMm.toString() ?? '—'),
                  if (v != null) kvRow(l10n.chargeable, kgStep(v.chargeableG)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(l10n.newValues, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 8),
          _numberField(_length, l10n.lengthMm),
          const SizedBox(height: 12),
          _numberField(_width, l10n.widthMm),
          const SizedBox(height: 12),
          _numberField(_height, l10n.heightMm),
          const SizedBox(height: 12),
          TextField(
            controller: _reason,
            decoration: InputDecoration(
                labelText: l10n.reason, border: const OutlineInputBorder()),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: Text(_busy ? l10n.saving : l10n.save),
          ),
        ],
      ),
    );
  }

  Widget _numberField(TextEditingController c, String label) => TextField(
        controller: c,
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        decoration: InputDecoration(
            labelText: label, border: const OutlineInputBorder()),
      );
}
