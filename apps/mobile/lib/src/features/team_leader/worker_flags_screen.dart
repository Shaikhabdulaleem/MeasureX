import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';

/// The review queue on mobile: open flags in the Team Leader's branch, with
/// approve / dismiss (PRD §11). Worker "Flag for Team Leader" actions appear here.
class WorkerFlagsScreen extends ConsumerStatefulWidget {
  const WorkerFlagsScreen({super.key});

  @override
  ConsumerState<WorkerFlagsScreen> createState() => _WorkerFlagsScreenState();
}

class _WorkerFlagsScreenState extends ConsumerState<WorkerFlagsScreen> {
  late Future<List<FlagModel>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<FlagModel>> _load() {
    final auth = ref.read(authControllerProvider);
    return ref.read(apiClientProvider).listFlags(auth.accessToken!);
  }

  void _refresh() => setState(() => _future = _load());

  Future<void> _resolve(FlagModel f, String action) async {
    final l10n = AppLocalizations.of(context);
    final auth = ref.read(authControllerProvider);
    try {
      await ref
          .read(apiClientProvider)
          .resolveFlag(auth.accessToken!, f.id, action);
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
      appBar: AppBar(title: Text(l10n.workerFlags)),
      body: RefreshIndicator(
        onRefresh: () async => _refresh(),
        child: FutureBuilder<List<FlagModel>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return _message(l10n.genericError);
            }
            final items = snapshot.data ?? [];
            if (items.isEmpty) return _message(l10n.noFlags);
            return ListView.separated(
              itemCount: items.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final f = items[i];
                return ListTile(
                  title: Text(f.awb ?? f.type),
                  subtitle:
                      Text('${f.type}${f.note != null ? ' · ${f.note}' : ''}'),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      TextButton(
                        onPressed: () => _resolve(f, 'approve'),
                        child: Text(l10n.approve),
                      ),
                      TextButton(
                        onPressed: () => _resolve(f, 'dismiss'),
                        child: Text(l10n.dismiss),
                      ),
                    ],
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
