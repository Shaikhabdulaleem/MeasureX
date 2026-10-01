import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import 'capture_controller.dart';
import 'scanner_screen.dart';
import 'widgets.dart';

/// Shipment summary with totals; "Scan next AWB" is the primary action (§5 step 11).
class ShipmentSummaryScreen extends ConsumerWidget {
  const ShipmentSummaryScreen({super.key, required this.shipment});
  final ShipmentModel shipment;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(automaticallyImplyLeading: false, title: Text(l10n.shipmentSummary)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(shipment.awb, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 16),
            totalsSummary(context, l10n, shipment.totals),
            const Spacer(),
            SizedBox(
              height: 64,
              child: FilledButton.icon(
                onPressed: () {
                  ref.read(captureControllerProvider.notifier).reset();
                  Navigator.of(context).popUntil((route) => route.isFirst);
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const ScannerScreen()),
                  );
                },
                icon: const Icon(Icons.qr_code_scanner),
                label: Text(l10n.scanNextAwb),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
