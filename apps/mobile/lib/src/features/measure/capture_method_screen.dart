import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import '../capture/capture_controller.dart';
import '../capture/manual_dimensions_screen.dart';
import '../capture/widgets.dart';
import 'measure_screen.dart';
import 'measurement_engine.dart';

/// After a scan, choose how to measure the package (PRD §4): the camera
/// marker-mat path (Phase B, shown as beta) or manual entry. The camera option
/// is offered only when the native engine is present; manual is always the
/// fallback. Device-tier gating is B2.
class CaptureMethodScreen extends ConsumerWidget {
  const CaptureMethodScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final number = ref.watch(captureControllerProvider).nextPackageNumber;
    final engineReady = ref.read(measurementEngineProvider).available;

    return Scaffold(
      appBar:
          AppBar(title: Text('${l10n.measure} — ${pkgLabel(l10n, number)}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (engineReady)
            Card(
              child: ListTile(
                leading: Icon(Icons.center_focus_strong,
                    color: Theme.of(context).colorScheme.primary),
                title: Text(l10n.measureWithCamera),
                subtitle: Text(l10n.measureWithCameraHint),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).pushReplacement(
                  MaterialPageRoute(builder: (_) => const MeasureScreen()),
                ),
              ),
            ),
          if (engineReady) const SizedBox(height: 12),
          Card(
            child: ListTile(
              leading: const Icon(Icons.edit),
              title: Text(l10n.enterManually),
              subtitle: Text(l10n.enterManuallyHint),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).pushReplacement(
                MaterialPageRoute(
                    builder: (_) => const ManualDimensionsScreen()),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
