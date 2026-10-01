import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import '../auth/auth_controller.dart';

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
              // Status placeholders (not wired in M0).
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
                  Expanded(
                    child: _StatusChip(
                      icon: Icons.scale,
                      label: t.scaleStatus,
                      value: t.statusNotConnected,
                    ),
                  ),
                ],
              ),
              const Spacer(),
              // Big primary action — not wired until M1.
              SizedBox(
                height: 96,
                child: FilledButton.icon(
                  onPressed: null,
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
