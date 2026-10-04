import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import '../capture/widgets.dart';
import 'correct_measurement_screen.dart';

/// Team Leader shipment detail: totals, each package, and the TL actions
/// Correct (per active package) and Reopen (when completed) — PRD §8, §11.
/// All actions call the shared API, which enforces role + branch server-side.
class TlShipmentDetailScreen extends ConsumerStatefulWidget {
  const TlShipmentDetailScreen({super.key, required this.awb});
  final String awb;

  @override
  ConsumerState<TlShipmentDetailScreen> createState() =>
      _TlShipmentDetailScreenState();
}

class _TlShipmentDetailScreenState
    extends ConsumerState<TlShipmentDetailScreen> {
  late Future<ShipmentDetail> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<ShipmentDetail> _load() {
    final auth = ref.read(authControllerProvider);
    return ref
        .read(apiClientProvider)
        .getShipment(auth.accessToken!, widget.awb);
  }

  void _refresh() => setState(() => _future = _load());

  Future<void> _reopen(ShipmentDetail s) async {
    final l10n = AppLocalizations.of(context);
    final reason = await _promptReason(context, l10n, l10n.reopenShipment);
    if (reason == null) return;
    final auth = ref.read(authControllerProvider);
    try {
      await ref
          .read(apiClientProvider)
          .reopenShipment(auth.accessToken!, s.awb, reason);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.shipmentReopened)));
      _refresh();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.actionFailed)));
    }
  }

  Future<void> _correct(PackageModel p) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => CorrectMeasurementScreen(package: p)),
    );
    if (changed == true) _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(widget.awb)),
      body: FutureBuilder<ShipmentDetail>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || !snapshot.hasData) {
            return Center(child: Text(l10n.genericError));
          }
          final s = snapshot.data!;
          final active = s.packages.where((p) => p.status == 'active').toList();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(s.status,
                      style: Theme.of(context).textTheme.titleMedium),
                  if (s.status == 'completed')
                    OutlinedButton.icon(
                      onPressed: () => _reopen(s),
                      icon: const Icon(Icons.lock_open, size: 18),
                      label: Text(l10n.reopen),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              totalsSummary(context, l10n, s.totals),
              const SizedBox(height: 20),
              ...active.map((p) {
                final v = p.currentVersion;
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(
                        child: Text((p.packageNumber ?? 0).toString())),
                    title: Text(pkgLabel(l10n, p.packageNumber ?? 0)),
                    subtitle: v == null
                        ? null
                        : Text(
                            '${v.billingLCm} × ${v.billingWCm} × ${v.billingHCm} cm\n'
                            '${l10n.cbm}: ${cbmStr(v.cbm)} · '
                            '${l10n.chargeable}: ${kgStep(v.chargeableG)}',
                          ),
                    isThreeLine: v != null,
                    trailing: TextButton(
                      onPressed: () => _correct(p),
                      child: Text(l10n.correct),
                    ),
                  ),
                );
              }),
            ],
          );
        },
      ),
    );
  }
}

/// Shared reason prompt used by Reopen (and any reason-required action).
Future<String?> _promptReason(
  BuildContext context,
  AppLocalizations l10n,
  String title,
) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: InputDecoration(labelText: l10n.reason),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
        FilledButton(
          onPressed: () {
            final text = controller.text.trim();
            if (text.isEmpty) return;
            Navigator.pop(context, text);
          },
          child: Text(l10n.submit),
        ),
      ],
    ),
  );
}
