import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import '../capture/widgets.dart';
import 'tl_shipment_detail_screen.dart';

/// Team history: shipments in the Team Leader's branch (PRD §3, §11). The
/// server scopes the list to the caller's branch.
class TeamHistoryScreen extends ConsumerStatefulWidget {
  const TeamHistoryScreen({super.key});

  @override
  ConsumerState<TeamHistoryScreen> createState() => _TeamHistoryScreenState();
}

class _TeamHistoryScreenState extends ConsumerState<TeamHistoryScreen> {
  late Future<List<ShipmentModel>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<ShipmentModel>> _load() {
    final auth = ref.read(authControllerProvider);
    // No employeeId filter → the server returns the whole branch for a TL.
    return ref.read(apiClientProvider).listShipments(auth.accessToken!);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.teamHistory)),
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
                  Center(child: Text(l10n.genericError))
                ],
              );
            }
            final items = snapshot.data ?? [];
            if (items.isEmpty) {
              return ListView(
                children: [
                  const SizedBox(height: 120),
                  Center(child: Text(l10n.noTeamHistory))
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
                    MaterialPageRoute(
                        builder: (_) => TlShipmentDetailScreen(awb: s.awb)),
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
