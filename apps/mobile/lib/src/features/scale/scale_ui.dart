import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import 'scale_controller.dart';
import 'scale_models.dart';
import 'scale_settings_screen.dart';

/// Localised label for a scale state (PRD §9 states).
String scaleStateLabel(AppLocalizations l10n, ScaleState state) {
  switch (state) {
    case ScaleState.connected:
      return l10n.scaleStateConnected;
    case ScaleState.connecting:
      return l10n.scaleStateConnecting;
    case ScaleState.disconnected:
      return l10n.scaleStateDisconnected;
    case ScaleState.reading:
      return l10n.scaleStateReading;
    case ScaleState.unstable:
      return l10n.scaleStateUnstable;
    case ScaleState.stable:
      return l10n.scaleStateStable;
    case ScaleState.error:
      return l10n.scaleStateError;
  }
}

Color scaleStateColor(BuildContext context, ScaleState state) {
  final scheme = Theme.of(context).colorScheme;
  switch (state) {
    case ScaleState.stable:
      return Colors.green.shade600;
    case ScaleState.unstable:
    case ScaleState.connecting:
    case ScaleState.reading:
      return Colors.orange.shade700;
    case ScaleState.error:
      return scheme.error;
    case ScaleState.connected:
      return scheme.primary;
    case ScaleState.disconnected:
      return scheme.outline;
  }
}

/// Compact scale status chip for Home and the capture screens (PRD §9). Tapping
/// it opens the Bluetooth Scale settings.
class ScaleStatusChip extends ConsumerWidget {
  const ScaleStatusChip({super.key, this.showWeight = false});

  /// When true, shows the live weight next to the state (used during capture).
  final bool showWeight;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final scale = ref.watch(scaleControllerProvider);
    final color = scaleStateColor(context, scale.state);

    final grams = scale.grams;
    final weightText = showWeight && grams != null ? '  ${(grams / 1000).toStringAsFixed(2)} kg' : '';

    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const ScaleSettingsScreen()),
      ),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          border: Border.all(color: color),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Icon(Icons.scale, size: 20, color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(l10n.scaleStatus, style: Theme.of(context).textTheme.labelSmall),
                  Text(
                    '${scaleStateLabel(l10n, scale.state)}$weightText',
                    style: Theme.of(context)
                        .textTheme
                        .bodyMedium
                        ?.copyWith(color: color, fontWeight: FontWeight.w600),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
