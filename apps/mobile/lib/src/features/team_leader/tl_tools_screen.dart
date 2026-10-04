import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import 'remeasure_queue_screen.dart';
import 'worker_flags_screen.dart';
import 'team_history_screen.dart';

/// Team Leader tools hub (PRD §11). Only reachable by team_leader / admin
/// (gated in the home screen); the API also enforces role + branch on every
/// endpoint these screens call.
class TlToolsScreen extends ConsumerWidget {
  const TlToolsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final tools = <_Tool>[
      _Tool(Icons.assignment_return, l10n.remeasureQueue,
          const RemeasureQueueScreen()),
      _Tool(Icons.flag, l10n.workerFlags, const WorkerFlagsScreen()),
      _Tool(Icons.history, l10n.teamHistory, const TeamHistoryScreen()),
    ];
    return Scaffold(
      appBar: AppBar(title: Text(l10n.teamLeaderTools)),
      body: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: tools.length,
        separatorBuilder: (_, __) => const SizedBox(height: 12),
        itemBuilder: (context, i) {
          final t = tools[i];
          return Card(
            child: ListTile(
              leading:
                  Icon(t.icon, color: Theme.of(context).colorScheme.primary),
              title: Text(t.label),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context)
                  .push(MaterialPageRoute(builder: (_) => t.screen)),
            ),
          );
        },
      ),
    );
  }
}

class _Tool {
  _Tool(this.icon, this.label, this.screen);
  final IconData icon;
  final String label;
  final Widget screen;
}
