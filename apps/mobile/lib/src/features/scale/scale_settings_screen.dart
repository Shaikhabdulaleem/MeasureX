import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../l10n/app_localizations.dart';
import 'scale_controller.dart';
import 'scale_ui.dart';
import 'test_weight_screen.dart';

/// Loads the approved scales (and auto-reconnects to the remembered one).
final approvedScalesProvider = FutureProvider.autoDispose<List<ScaleModel>>((ref) async {
  return ref.read(scaleControllerProvider.notifier).loadScales();
});

/// Settings → Bluetooth Scale (PRD §9): choose a scale, pair once per station
/// (remembered + auto-reconnect), and open the Test weight screen.
class ScaleSettingsScreen extends ConsumerWidget {
  const ScaleSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final scalesAsync = ref.watch(approvedScalesProvider);
    final runtime = ref.watch(scaleControllerProvider);
    final controller = ref.read(scaleControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.bluetoothScale)),
      body: scalesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => Center(child: Text(l10n.loadScalesFailed)),
        data: (scales) {
          if (scales.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.noApprovedScales, textAlign: TextAlign.center),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(l10n.selectScale,
                    style: Theme.of(context).textTheme.titleMedium),
              ),
              for (final scale in scales)
                ListTile(
                  leading: Icon(
                    runtime.scale?.id == scale.id
                        ? Icons.radio_button_checked
                        : Icons.radio_button_unchecked,
                    color: runtime.scale?.id == scale.id
                        ? Theme.of(context).colorScheme.primary
                        : null,
                  ),
                  title: Text(scale.model),
                  subtitle: Text('${scale.connection.toUpperCase()} · ${scale.adapterKey}'),
                  onTap: () => controller.select(scale),
                ),
              const Divider(height: 24),
              _StatusRow(runtime: runtime),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 56,
                      child: runtime.isConnected
                          ? OutlinedButton.icon(
                              onPressed: () => controller.disconnect(),
                              icon: const Icon(Icons.bluetooth_disabled),
                              label: Text(l10n.disconnect),
                            )
                          : FilledButton.icon(
                              onPressed: runtime.scale == null ? null : () => controller.connect(),
                              icon: const Icon(Icons.bluetooth_connected),
                              label: Text(l10n.connect),
                            ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: SizedBox(
                      height: 56,
                      child: OutlinedButton.icon(
                        onPressed: runtime.scale == null
                            ? null
                            : () => Navigator.of(context).push(
                                  MaterialPageRoute(builder: (_) => const TestWeightScreen()),
                                ),
                        icon: const Icon(Icons.monitor_weight),
                        label: Text(l10n.testWeight),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  const _StatusRow({required this.runtime});
  final ScaleRuntime runtime;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final color = scaleStateColor(context, runtime.state);
    return Row(
      children: [
        Icon(Icons.circle, size: 12, color: color),
        const SizedBox(width: 8),
        Text(scaleStateLabel(l10n, runtime.state),
            style: TextStyle(color: color, fontWeight: FontWeight.w600)),
        if (runtime.deviceLabel != null) ...[
          const SizedBox(width: 8),
          Text('· ${runtime.deviceLabel}', style: Theme.of(context).textTheme.bodySmall),
        ],
      ],
    );
  }
}
