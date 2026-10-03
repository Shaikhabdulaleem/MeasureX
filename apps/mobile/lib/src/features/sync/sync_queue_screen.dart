import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/db/app_database.dart';
import 'sync_providers.dart';

/// Sync Queue (PRD §5, §10): counts by state + a Retry for failed/conflict
/// records. English-only for M3 (localisation is M5).
class SyncQueueScreen extends ConsumerWidget {
  const SyncQueueScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(syncStatusProvider).valueOrNull ?? SyncStatus.empty;
    final hasRetryable = status.failed + status.conflict > 0;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Sync queue'),
        actions: [
          IconButton(
            tooltip: 'Retry all',
            icon: const Icon(Icons.refresh),
            onPressed: hasRetryable
                ? () => ref.read(syncEngineProvider).retryAll()
                : null,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _CountTile(label: 'Pending', value: status.pending, icon: Icons.schedule),
          _CountTile(label: 'Syncing', value: status.syncing, icon: Icons.sync),
          _CountTile(label: 'Synced', value: status.synced, icon: Icons.cloud_done),
          _CountTile(
            label: 'Failed',
            value: status.failed,
            icon: Icons.error_outline,
            emphasise: status.failed > 0,
          ),
          _CountTile(
            label: 'Conflict (Team Leader)',
            value: status.conflict,
            icon: Icons.flag,
            emphasise: status.conflict > 0,
          ),
          const SizedBox(height: 24),
          if (hasRetryable)
            FilledButton.icon(
              onPressed: () => ref.read(syncEngineProvider).retryAll(),
              icon: const Icon(Icons.refresh),
              label: const Text('Retry failed & conflicts'),
            ),
          const SizedBox(height: 24),
          const _QueueList(),
        ],
      ),
    );
  }
}

class _QueueList extends ConsumerWidget {
  const _QueueList();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final db = ref.watch(appDatabaseProvider);
    return StreamBuilder<List<SyncQueueData>>(
      stream: db.watchQueue(),
      builder: (context, snapshot) {
        final rows = snapshot.data ?? const [];
        if (rows.isEmpty) {
          return const Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: Text('Nothing in the queue.')),
          );
        }
        return Column(
          children: [
            for (final r in rows)
              ListTile(
                dense: true,
                leading: Icon(_iconFor(r.status)),
                title: Text(r.packageId, overflow: TextOverflow.ellipsis),
                subtitle: Text(
                  r.lastError == null ? r.status : '${r.status} — ${r.lastError}',
                ),
                trailing: (r.status == SyncState.failed || r.status == SyncState.conflict)
                    ? TextButton(
                        onPressed: () => ref.read(syncEngineProvider).retryAll(),
                        child: const Text('Retry'),
                      )
                    : null,
              ),
          ],
        );
      },
    );
  }

  IconData _iconFor(String status) {
    switch (status) {
      case SyncState.synced:
        return Icons.cloud_done;
      case SyncState.syncing:
        return Icons.sync;
      case SyncState.failed:
        return Icons.error_outline;
      case SyncState.conflict:
        return Icons.flag;
      default:
        return Icons.schedule;
    }
  }
}

class _CountTile extends StatelessWidget {
  const _CountTile({
    required this.label,
    required this.value,
    required this.icon,
    this.emphasise = false,
  });

  final String label;
  final int value;
  final IconData icon;
  final bool emphasise;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        leading: Icon(icon, color: emphasise ? scheme.error : null),
        title: Text(label),
        trailing: Text(
          '$value',
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                color: emphasise ? scheme.error : null,
              ),
        ),
      ),
    );
  }
}
