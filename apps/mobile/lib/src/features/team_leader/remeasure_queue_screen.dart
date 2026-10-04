import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import 'tl_shipment_detail_screen.dart';

/// Open remeasurement requests in the Team Leader's branch (PRD §11).
class RemeasureQueueScreen extends ConsumerStatefulWidget {
  const RemeasureQueueScreen({super.key});

  @override
  ConsumerState<RemeasureQueueScreen> createState() =>
      _RemeasureQueueScreenState();
}

class _RemeasureQueueScreenState extends ConsumerState<RemeasureQueueScreen> {
  late Future<List<RemeasureRequestModel>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<RemeasureRequestModel>> _load() {
    final auth = ref.read(authControllerProvider);
    return ref.read(apiClientProvider).listRemeasurements(auth.accessToken!);
  }

  void _refresh() => setState(() => _future = _load());

  Future<void> _cancel(RemeasureRequestModel r) async {
    final l10n = AppLocalizations.of(context);
    final auth = ref.read(authControllerProvider);
    try {
      await ref
          .read(apiClientProvider)
          .cancelRemeasure(auth.accessToken!, r.id);
      if (!mounted) return;
      _refresh();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.actionFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.remeasureQueue)),
      body: RefreshIndicator(
        onRefresh: () async => _refresh(),
        child: FutureBuilder<List<RemeasureRequestModel>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return _message(l10n.genericError);
            }
            final items = snapshot.data ?? [];
            if (items.isEmpty) return _message(l10n.noRemeasurements);
            return ListView.separated(
              itemCount: items.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final r = items[i];
                return ListTile(
                  title: Text(r.awb ?? r.shipmentId),
                  subtitle: Text(
                      '${r.reason}${r.note != null ? ' · ${r.note}' : ''}'),
                  trailing: TextButton(
                    onPressed: () => _cancel(r),
                    child: Text(l10n.cancelRequest),
                  ),
                  onTap: r.awb == null
                      ? null
                      : () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) =>
                                  TlShipmentDetailScreen(awb: r.awb!),
                            ),
                          ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  Widget _message(String text) => ListView(
        children: [const SizedBox(height: 120), Center(child: Text(text))],
      );
}
