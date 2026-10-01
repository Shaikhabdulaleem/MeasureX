import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import 'capture_controller.dart';
import 'manual_dimensions_screen.dart';
import 'shipment_summary_screen.dart';
import 'widgets.dart';

/// "Package saved" → Add another package / Complete shipment (PRD §5 step 10).
class PackageSavedScreen extends ConsumerStatefulWidget {
  const PackageSavedScreen({super.key, required this.packageNumber});
  final int packageNumber;

  @override
  ConsumerState<PackageSavedScreen> createState() => _PackageSavedScreenState();
}

class _PackageSavedScreenState extends ConsumerState<PackageSavedScreen> {
  bool _completing = false;

  void _addAnother() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const ManualDimensionsScreen()),
    );
  }

  Future<void> _complete() async {
    final l10n = AppLocalizations.of(context);
    setState(() => _completing = true);
    try {
      final shipment = await ref.read(captureControllerProvider.notifier).complete();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => ShipmentSummaryScreen(shipment: shipment)),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _completing = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.genericError)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(automaticallyImplyLeading: false, title: Text(l10n.packageSaved)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 24),
            Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary, size: 72),
            const SizedBox(height: 16),
            Text(
              '${pkgLabel(l10n, widget.packageNumber)} — ${l10n.packageSaved}',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const Spacer(),
            SizedBox(
              height: 60,
              child: OutlinedButton.icon(
                onPressed: _completing ? null : _addAnother,
                icon: const Icon(Icons.add_box),
                label: Text(l10n.addAnotherPackage),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 60,
              child: FilledButton.icon(
                onPressed: _completing ? null : _complete,
                icon: const Icon(Icons.done_all),
                label: Text(_completing ? l10n.saving : l10n.completeShipment),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
