import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import 'widgets.dart';

/// Shown when a scanned AWB belongs to an already-completed shipment (PRD §5):
/// previous result read-only, plus "Flag for Team Leader" (Labour) or
/// "Remeasure" (Team Leader / Admin).
Future<void> showPreviousResultSheet(
  BuildContext context,
  WidgetRef ref,
  ShipmentDetail shipment,
) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) => _PreviousResultSheet(shipment: shipment),
  );
}

class _PreviousResultSheet extends ConsumerStatefulWidget {
  const _PreviousResultSheet({required this.shipment});
  final ShipmentDetail shipment;

  @override
  ConsumerState<_PreviousResultSheet> createState() => _PreviousResultSheetState();
}

class _PreviousResultSheetState extends ConsumerState<_PreviousResultSheet> {
  bool _busy = false;

  String get _token => ref.read(authControllerProvider).accessToken!;

  Future<void> _flag() async {
    final l10n = AppLocalizations.of(context);
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).flagShipment(_token, widget.shipment.id);
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.flaggedDone)));
    } catch (_) {
      if (mounted) setState(() => _busy = false);
      _error();
    }
  }

  Future<void> _remeasure() async {
    final l10n = AppLocalizations.of(context);
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).requestRemeasure(
            _token,
            widget.shipment.id,
            widget.shipment.packages.map((p) => p.id).toList(),
            'manual_verification',
          );
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.remeasureRequested)));
    } catch (_) {
      if (mounted) setState(() => _busy = false);
      _error();
    }
  }

  void _error() {
    final l10n = AppLocalizations.of(context);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.genericError)));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final role = ref.read(authControllerProvider).user?.role ?? 'labour';
    final totals = widget.shipment.totals;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        4,
        20,
        20 + MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.shipment.awb, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text(l10n.shipmentCompletedMsg,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
          const SizedBox(height: 16),
          totalsSummary(context, l10n, totals),
          const SizedBox(height: 20),
          if (_busy)
            const Center(child: Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator()))
          else if (role == 'labour')
            SizedBox(
              width: double.infinity,
              height: 56,
              child: FilledButton.icon(
                onPressed: _flag,
                icon: const Icon(Icons.flag),
                label: Text(l10n.flagForTeamLeader),
              ),
            )
          else
            SizedBox(
              width: double.infinity,
              height: 56,
              child: FilledButton.icon(
                onPressed: _remeasure,
                icon: const Icon(Icons.straighten),
                label: Text(l10n.remeasure),
              ),
            ),
        ],
      ),
    );
  }
}
