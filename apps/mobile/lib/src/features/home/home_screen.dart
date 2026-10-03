import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../auth/auth_controller.dart';
import '../capture/scanner_screen.dart';
import '../history/history_screen.dart';
import '../scale/scale_settings_screen.dart';
import '../scale/scale_ui.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = AppLocalizations.of(context);
    final user = ref.watch(authControllerProvider).user;

    return Scaffold(
      appBar: AppBar(
        title: Text(t.appName),
        actions: [
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
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: SafeArea(
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
                      value: t.statusIdle,
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Live scale status (PRD §9) — tap to open scale settings.
                  const Expanded(child: ScaleStatusChip()),
                ],
              ),
              const Spacer(),
              // Big primary action — start the scan & capture flow.
              SizedBox(
                height: 96,
                child: FilledButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const ScannerScreen()),
                  ),
                  icon: const Icon(Icons.qr_code_scanner, size: 32),
                  label: Text(
                    t.scanShipment,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.icon, required this.label, required this.value});

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
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelSmall),
              Text(value, style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ],
      ),
    );
  }
}
