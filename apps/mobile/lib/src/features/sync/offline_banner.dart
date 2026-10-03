import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/connectivity.dart';
import 'sync_providers.dart';

// M3 strings are English-only; Arabic/Bengali localisation is M5 (PRD §16).
const kOfflineBanner =
    'OFFLINE MODE — measurements are saved on this phone and will sync automatically.';
const kOfflineCannotVerify = "Previous measurements can't be checked while offline.";
const kUnsyncedTooLong =
    'Some measurements have been waiting to sync for over 4 hours.';
const kStorageHigh = 'Local storage is filling up (over 500 MB of photos not yet synced).';

/// A thin status strip shown above capture/home: offline notice, plus the
/// >4 h-unsynced and >500 MB warnings (PRD §10 rule 8). Renders nothing when
/// online and healthy. On reconnect it also nudges the sync engine.
class OfflineBanner extends ConsumerWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Reconnect → flush immediately.
    ref.listen(onlineProvider, (prev, next) {
      final wasOffline = prev?.valueOrNull == false;
      final nowOnline = next.valueOrNull == true;
      if (wasOffline && nowOnline) {
        ref.read(syncEngineProvider).runNow();
      }
    });

    final online = ref.watch(onlineProvider).valueOrNull ?? true;
    final status = ref.watch(syncStatusProvider).valueOrNull ?? SyncStatus.empty;

    final messages = <(_Severity, String)>[
      if (!online) (_Severity.info, kOfflineBanner),
      if (status.staleWarning) (_Severity.warn, kUnsyncedTooLong),
      if (status.storageWarning) (_Severity.warn, kStorageHigh),
    ];
    if (messages.isEmpty) return const SizedBox.shrink();

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [for (final m in messages) _Bar(severity: m.$1, text: m.$2)],
    );
  }
}

enum _Severity { info, warn }

class _Bar extends StatelessWidget {
  const _Bar({required this.severity, required this.text});
  final _Severity severity;
  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final bg = severity == _Severity.warn ? scheme.errorContainer : scheme.secondaryContainer;
    final fg = severity == _Severity.warn ? scheme.onErrorContainer : scheme.onSecondaryContainer;
    final icon = severity == _Severity.warn ? Icons.warning_amber : Icons.cloud_off;
    return Container(
      width: double.infinity,
      color: bg,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Icon(icon, size: 18, color: fg),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: TextStyle(color: fg, fontSize: 13))),
        ],
      ),
    );
  }
}
