import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import '../capture/widgets.dart';

/// Shipment detail: totals + each package's dimensions and billing.
class ShipmentDetailScreen extends ConsumerStatefulWidget {
  const ShipmentDetailScreen({super.key, required this.awb});
  final String awb;

  @override
  ConsumerState<ShipmentDetailScreen> createState() => _ShipmentDetailScreenState();
}

class _ShipmentDetailScreenState extends ConsumerState<ShipmentDetailScreen> {
  late Future<ShipmentDetail> _future;

  @override
  void initState() {
    super.initState();
    final auth = ref.read(authControllerProvider);
    _future = ref.read(apiClientProvider).getShipment(auth.accessToken!, widget.awb);
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
              Text(s.status, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              totalsSummary(context, l10n, s.totals),
              const SizedBox(height: 20),
              ...active.map((p) {
                final v = p.currentVersion;
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(
                      child: Text((p.packageNumber ?? 0).toString()),
                    ),
                    title: Text(pkgLabel(l10n, p.packageNumber ?? 0)),
                    subtitle: v == null
                        ? null
                        : Text(
                            '${v.billingLCm} × ${v.billingWCm} × ${v.billingHCm} cm\n'
                            '${l10n.cbm}: ${cbmStr(v.cbm)} · '
                            '${l10n.chargeable}: ${kgStep(v.chargeableG)}',
                          ),
                    isThreeLine: v != null,
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
