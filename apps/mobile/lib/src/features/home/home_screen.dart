import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../auth/auth_controller.dart';
import '../capture/scanner_screen.dart';
import '../history/history_screen.dart';
import '../scale/scale_settings_screen.dart';
import '../scale/scale_ui.dart';
import '../team_leader/tl_tools_screen.dart';
import '../sync/offline_banner.dart';
import '../sync/sync_providers.dart';
import '../sync/sync_queue_screen.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = AppLocalizations.of(context);
    final user = ref.watch(authControllerProvider).user;
    // Start the sync engine's periodic pump for the lifetime of the session.
    ref.watch(syncEngineProvider);
    final status =
        ref.watch(syncStatusProvider).valueOrNull ?? SyncStatus.empty;

    return Scaffold(
      appBar: AppBar(
        title: Text(t.appName),
        actions: [
          IconButton(
            tooltip: 'Sync queue',
            icon: Badge(
              isLabelVisible: status.unsynced > 0,
              label: Text('${status.unsynced}'),
              child: const Icon(Icons.sync),
            ),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SyncQueueScreen()),
            ),
          ),
          IconButton(
            tooltip: t.history,
            icon: const Icon(Icons.history),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const HistoryScreen()),
            ),
          ),
          IconButton(
            tooltip: t.bluetoothScale,
            icon: const Icon(Icons.scale),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ScaleSettingsScreen()),
            ),
          ),
          IconButton(
            tooltip: t.signOut,
            icon: const Icon(Icons.logout),
            onPressed: () => _handleLogout(context, ref),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            const OfflineBanner(),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (user != null)
                      Text('${t.welcome}, ${user.name}',
                          style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 24),
                    Row(
                      children: [
                        Expanded(
                          child: _StatusChip(
                            icon: Icons.sync,
                            label: t.syncStatus,
                            value: status.unsynced == 0
                                ? t.statusIdle
                                : '${status.unsynced} to sync',
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(child: ScaleStatusChip()),
                      ],
                    ),
                    const Spacer(),
                    SizedBox(
                      height: 96,
                      child: FilledButton.icon(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                              builder: (_) => const ScannerScreen()),
                        ),
                        icon: const Icon(Icons.qr_code_scanner, size: 32),
                        label: Text(
                          t.scanShipment,
                          style: const TextStyle(
                              fontSize: 22, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ),
                    if (user != null &&
                        (user.role == 'team_leader' ||
                            user.role == 'admin')) ...[
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                              builder: (_) => const TlToolsScreen()),
                        ),
                        icon: const Icon(Icons.supervisor_account),
                        label: Text(t.teamLeaderTools),
                      ),
                    ],
                    const Spacer(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Logout respecting unsynced records (PRD §3, §10 rule 7): wipe local data
  /// only when everything is synced; otherwise warn and keep it on the device.
  Future<void> _handleLogout(BuildContext context, WidgetRef ref) async {
    final db = ref.read(appDatabaseProvider);
    final hasUnsynced = await db.hasUnsynced();
    if (!context.mounted) return;

    var proceed = true;
    if (hasUnsynced) {
      proceed = await showDialog<bool>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('Unsynced measurements'),
              content: const Text(
                'Some measurements have not synced yet. If you log out now they '
                'stay on this device under your account and will sync when you '
                'sign in again. Log out anyway?',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: const Text('Log out'),
                ),
              ],
            ),
          ) ??
          false;
    }
    if (!proceed) return;
    await ref
        .read(authControllerProvider.notifier)
        .logout(wipeLocal: !hasUnsynced);
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip(
      {required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelSmall),
                Text(value,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
