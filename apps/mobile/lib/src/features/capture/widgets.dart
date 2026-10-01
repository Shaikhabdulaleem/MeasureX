import 'package:flutter/material.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';

/// "PKG 01" style label (Western digits in all languages, PRD §15).
String pkgLabel(AppLocalizations l10n, int number) =>
    '${l10n.pkg} ${number.toString().padLeft(2, '0')}';

String kg(int grams) => '${(grams / 1000).toStringAsFixed(2)} kg';
String kgStep(int grams) => '${(grams / 1000).toStringAsFixed(1)} kg';
String cbmStr(double cbm) => cbm.toStringAsFixed(4);

/// A labelled value row used across review / summary.
Widget kvRow(String label, String value, {bool emphasise = false}) {
  return Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontSize: 16)),
        Text(
          value,
          style: TextStyle(
            fontSize: 16,
            fontWeight: emphasise ? FontWeight.bold : FontWeight.w500,
          ),
        ),
      ],
    ),
  );
}

/// Shipment totals block (pieces, CBM, volumetric, chargeable).
Widget totalsSummary(BuildContext context, AppLocalizations l10n, ShipmentTotals totals) {
  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      children: [
        kvRow(l10n.packages, totals.pieces.toString()),
        kvRow(l10n.cbm, cbmStr(totals.cbm)),
        kvRow(l10n.volumetric, kg(totals.volumetricG)),
        kvRow(l10n.chargeable, kgStep(totals.chargeableG), emphasise: true),
      ],
    ),
  );
}
