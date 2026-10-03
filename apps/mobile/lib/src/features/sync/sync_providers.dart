import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/db/app_database.dart';
import '../../core/db/db_providers.dart';
import '../auth/auth_controller.dart';
import 'sync_engine.dart';

// Re-export so existing imports of `appDatabaseProvider` via this file resolve.
export '../../core/db/db_providers.dart' show appDatabaseProvider, dbKeyStoreProvider;

/// The long-lived sync engine. Starts its 60 s pump on first read.
final syncEngineProvider = Provider<SyncEngine>((ref) {
  final engine = SyncEngine(
    db: ref.watch(appDatabaseProvider),
    api: ref.watch(apiClientProvider),
    token: () => ref.read(authControllerProvider).accessToken,
  );
  engine.start();
  ref.onDispose(engine.stop);
  return engine;
});

/// Thresholds for the unsynced warnings (PRD §10 rule 8).
const kUnsyncedWarnAfter = Duration(hours: 4);
const kStorageWarnBytes = 500 * 1024 * 1024; // 500 MB

class SyncStatus {
  const SyncStatus({
    required this.pending,
    required this.syncing,
    required this.synced,
    required this.failed,
    required this.conflict,
    required this.oldestUnsyncedAt,
    required this.pendingPhotoBytes,
  });

  final int pending;
  final int syncing;
  final int synced;
  final int failed;
  final int conflict;
  final DateTime? oldestUnsyncedAt;
  final int pendingPhotoBytes;

  int get unsynced => pending + syncing + failed + conflict;

  bool get staleWarning =>
      oldestUnsyncedAt != null &&
      DateTime.now().difference(oldestUnsyncedAt!) > kUnsyncedWarnAfter;

  bool get storageWarning => pendingPhotoBytes > kStorageWarnBytes;

  static const empty = SyncStatus(
    pending: 0,
    syncing: 0,
    synced: 0,
    failed: 0,
    conflict: 0,
    oldestUnsyncedAt: null,
    pendingPhotoBytes: 0,
  );
}

/// Reactive sync status (counts + warnings) derived from the queue table.
final syncStatusProvider = StreamProvider<SyncStatus>((ref) {
  final db = ref.watch(appDatabaseProvider);
  return db.watchQueue().asyncMap((rows) async {
    int count(String s) => rows.where((r) => r.status == s).length;
    return SyncStatus(
      pending: count(SyncState.pending),
      syncing: count(SyncState.syncing),
      synced: count(SyncState.synced),
      failed: count(SyncState.failed),
      conflict: count(SyncState.conflict),
      oldestUnsyncedAt: await db.oldestUnsyncedAt(),
      pendingPhotoBytes: await db.pendingPhotoBytes(),
    );
  });
});
