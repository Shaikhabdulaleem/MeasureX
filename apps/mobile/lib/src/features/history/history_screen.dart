import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import '../capture/widgets.dart';
import 'shipment_detail_screen.dart';

/// Own measurements, last 7 days (PRD §3). The server scopes the list.
class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  late Future<List<ShipmentModel>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<ShipmentModel>> _load() {
    final auth = ref.read(authControllerProvider);
    final since = DateTime.now().toUtc().subtract(const Duration(days: 7));
    return ref.read(apiClientProvider).listShipments(
          auth.accessToken!,
          employeeId: auth.user?.id,
          dateFrom: since.toIso8601String(),
        );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.history)),
      body: RefreshIndicator(
        onRefresh: () async => setState(() => _future = _load()),
        child: FutureBuilder<List<ShipmentModel>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return ListView(
                children: [
                  const SizedBox(height: 120),
                  Center(child: Text(l10n.genericError)),
                ],
              );
            }
            final items = snapshot.data ?? [];
            if (items.isEmpty) {
              return ListView(
                children: [
                  const SizedBox(height: 120),
                  Center(child: Text(l10n.noRecentHistory)),
                ],
              );
            }
            return ListView.separated(
              itemCount: items.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final s = items[i];
                return ListTile(
                  title: Text(s.awb),
                  subtitle: Text(
                    '${s.status} · ${l10n.packages}: ${s.totals.pieces} · '
                    '${l10n.chargeable}: ${kgStep(s.totals.chargeableG)}',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => ShipmentDetailScreen(awb: s.awb)),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
