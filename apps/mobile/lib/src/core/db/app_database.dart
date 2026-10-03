import 'dart:ffi';
import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlite3/open.dart';
import 'package:sqlcipher_flutter_libs/sqlcipher_flutter_libs.dart';

part 'app_database.g.dart';

/// A sync-queue row joined with its package's owner, for the Sync Queue UI.
class QueueRow {
  const QueueRow({
    required this.packageId,
    required this.status,
    required this.awb,
    required this.provisionalNumber,
    this.serverNumber,
    this.lastError,
    this.ownerUserId,
    this.ownerName,
  });

  final String packageId;
  final String status;
  final String awb;
  final int provisionalNumber;
  final int? serverNumber;
  final String? lastError;
  final String? ownerUserId;
  final String? ownerName;
}

/// Sync-record states (PRD §8 sync state machine). Stored as text.
class SyncState {
  static const pending = 'pending';
  static const syncing = 'syncing';
  static const synced = 'synced';
  static const failed = 'failed';
  static const conflict = 'conflict';
}

/// One shipment seen on this device (keyed by AWB). Local mirror only.
@DataClassName('LocalShipment')
class LocalShipments extends Table {
  TextColumn get awb => text()();
  TextColumn get status => text().withDefault(const Constant('in_progress'))();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {awb};
}

/// A package saved on this device. `id` is the client UUID sent to the server;
/// `serverPackageNumber` is null until the server assigns the final number
/// (until then the UI shows the provisional number as "PKG 02*").
@DataClassName('LocalPackage')
class LocalPackages extends Table {
  TextColumn get id => text()();
  TextColumn get awb => text()();
  IntColumn get provisionalNumber => integer()();
  IntColumn get serverPackageNumber => integer().nullable()();
  IntColumn get lengthMm => integer()();
  IntColumn get widthMm => integer()();
  IntColumn get heightMm => integer()();
  IntColumn get actualWeightG => integer().nullable()();
  TextColumn get weightSource => text().withDefault(const Constant('none'))();
  TextColumn get weightReason => text().nullable()();
  TextColumn get scaleId => text().nullable()();
  TextColumn get method => text().withDefault(const Constant('manual'))();
  TextColumn get confidence => text().nullable()();
  TextColumn get deviceId => text().nullable()();
  // Shared phones (PRD §3): the user who measured this package. The sync engine
  // only uploads the logged-in user's own records; others stay on the device.
  TextColumn get measuredByUserId => text().nullable()();
  TextColumn get measuredByName => text().nullable()();
  TextColumn get idempotencyKey => text()();
  DateTimeColumn get confirmedAt => dateTime()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

/// The photo for a package (one per package in M3). Stored as a file on disk;
/// `uploaded` flips true once the bytes reach object storage — a package is
/// only `synced` after that (PRD §10 rule 4).
@DataClassName('LocalPhoto')
class LocalPhotos extends Table {
  TextColumn get packageId => text()();
  TextColumn get filePath => text()();
  IntColumn get bytes => integer().withDefault(const Constant(0))();
  BoolColumn get uploaded => boolean().withDefault(const Constant(false))();
  // The server photo id, set after the first upload-target request. On retry we
  // refresh the URL for THIS id instead of creating a new photo row (PRD §10).
  TextColumn get photoId => text().nullable()();
  TextColumn get measuredByUserId => text().nullable()();

  @override
  Set<Column> get primaryKey => {packageId};
}

/// Telemetry events queued for /events/batch (append-only).
@DataClassName('LocalEvent')
class LocalEvents extends Table {
  TextColumn get id => text()();
  TextColumn get type => text()();
  TextColumn get awb => text().nullable()();
  TextColumn get payloadJson => text().nullable()();
  TextColumn get deviceId => text().nullable()();
  TextColumn get measuredByUserId => text().nullable()();
  DateTimeColumn get occurredAt => dateTime()();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();

  @override
  Set<Column> get primaryKey => {id};
}

/// Per-package sync record (PRD §8). One row per local package.
@DataClassName('SyncQueueData')
class SyncQueue extends Table {
  TextColumn get packageId => text()();
  TextColumn get status => text().withDefault(const Constant(SyncState.pending))();
  IntColumn get attempts => integer().withDefault(const Constant(0))();
  DateTimeColumn get nextAttemptAt => dateTime().nullable()();
  TextColumn get lastError => text().nullable()();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {packageId};
}

@DriftDatabase(
  tables: [LocalShipments, LocalPackages, LocalPhotos, LocalEvents, SyncQueue],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.e);

  /// Production: open the encrypted database file under the app's documents dir.
  factory AppDatabase.encrypted(String key) {
    return AppDatabase(_openEncrypted(key));
  }

  /// Tests: a plain in-memory database (no SQLCipher).
  factory AppDatabase.memory() => AppDatabase(NativeDatabase.memory());

  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) => m.createAll(),
        onUpgrade: (m, from, to) async {
          if (from < 2) {
            // Shared-phone ownership + photo id / retry support (PRD §3, §10).
            await m.addColumn(localPackages, localPackages.measuredByUserId);
            await m.addColumn(localPackages, localPackages.measuredByName);
            await m.addColumn(localPhotos, localPhotos.photoId);
            await m.addColumn(localPhotos, localPhotos.measuredByUserId);
            await m.addColumn(localEvents, localEvents.measuredByUserId);
          }
        },
      );

  // --- writes --------------------------------------------------------------

  /// Save a package + its photo locally and enqueue it for sync, atomically.
  Future<void> savePackageForSync({
    required LocalPackagesCompanion package,
    required String awb,
    required String photoPath,
    required int photoBytes,
  }) {
    return transaction(() async {
      await into(localShipments).insertOnConflictUpdate(
        LocalShipmentsCompanion.insert(awb: awb),
      );
      await into(localPackages).insert(package, mode: InsertMode.insertOrIgnore);
      await into(localPhotos).insert(
        LocalPhotosCompanion.insert(
          packageId: package.id.value,
          filePath: photoPath,
          bytes: Value(photoBytes),
          measuredByUserId: package.measuredByUserId,
        ),
        mode: InsertMode.insertOrIgnore,
      );
      await into(syncQueue).insert(
        SyncQueueCompanion.insert(packageId: package.id.value),
        mode: InsertMode.insertOrIgnore,
      );
    });
  }

  /// The next provisional number for an AWB on this device (count + 1).
  Future<int> nextProvisionalNumber(String awb) async {
    final countExp = localPackages.id.count();
    final count = await (selectOnly(localPackages)
          ..addColumns([countExp])
          ..where(localPackages.awb.equals(awb)))
        .map((row) => row.read(countExp) ?? 0)
        .getSingle();
    return count + 1;
  }

  Future<List<SyncQueueData>> recordsWithStatus(String status) {
    return (select(syncQueue)..where((r) => r.status.equals(status))).get();
  }

  /// Packages owned by [userId] that are due to be attempted now: pending, or
  /// failed whose backoff window has elapsed. Only the logged-in user's own
  /// records are uploaded (PRD §3 shared phones).
  Future<List<LocalPackage>> packagesDueForUser(DateTime now, String userId) async {
    final q = select(localPackages).join([
      innerJoin(syncQueue, syncQueue.packageId.equalsExp(localPackages.id)),
    ])
      ..where(
        localPackages.measuredByUserId.equals(userId) &
            (syncQueue.status.equals(SyncState.pending) |
                (syncQueue.status.equals(SyncState.failed) &
                    (syncQueue.nextAttemptAt.isSmallerOrEqualValue(now) |
                        syncQueue.nextAttemptAt.isNull()))),
      );
    final rows = await q.get();
    return rows.map((r) => r.readTable(localPackages)).toList();
  }

  Future<void> setPhotoId(String packageId, String photoId) {
    return (update(localPhotos)..where((p) => p.packageId.equals(packageId)))
        .write(LocalPhotosCompanion(photoId: Value(photoId)));
  }

  Future<LocalPhoto?> photoFor(String packageId) {
    return (select(localPhotos)..where((p) => p.packageId.equals(packageId)))
        .getSingleOrNull();
  }

  Future<void> setStatus(String packageId, String status) {
    return (update(syncQueue)..where((r) => r.packageId.equals(packageId))).write(
      SyncQueueCompanion(status: Value(status), updatedAt: Value(DateTime.now())),
    );
  }

  Future<void> markSyncing(List<String> ids) {
    return (update(syncQueue)..where((r) => r.packageId.isIn(ids))).write(
      SyncQueueCompanion(status: const Value(SyncState.syncing), updatedAt: Value(DateTime.now())),
    );
  }

  Future<void> markSynced(String packageId, int? serverNumber) {
    return transaction(() async {
      if (serverNumber != null) {
        await (update(localPackages)..where((p) => p.id.equals(packageId)))
            .write(LocalPackagesCompanion(serverPackageNumber: Value(serverNumber)));
      }
      await setStatus(packageId, SyncState.synced);
    });
  }

  Future<void> markFailed(String packageId, String error, DateTime nextAttemptAt) async {
    final attempts = await _attempts(packageId);
    await (update(syncQueue)..where((r) => r.packageId.equals(packageId))).write(
      SyncQueueCompanion(
        status: const Value(SyncState.failed),
        attempts: Value(attempts + 1),
        lastError: Value(error),
        nextAttemptAt: Value(nextAttemptAt),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  Future<void> markConflict(String packageId, int? serverNumber) {
    return transaction(() async {
      if (serverNumber != null) {
        await (update(localPackages)..where((p) => p.id.equals(packageId)))
            .write(LocalPackagesCompanion(serverPackageNumber: Value(serverNumber)));
      }
      await setStatus(packageId, SyncState.conflict);
    });
  }

  Future<void> markPhotoUploaded(String packageId) {
    return (update(localPhotos)..where((p) => p.packageId.equals(packageId)))
        .write(const LocalPhotosCompanion(uploaded: Value(true)));
  }

  /// Reset failed/conflict records to pending for an immediate manual retry.
  Future<void> retryAll() {
    return (update(syncQueue)
          ..where((r) =>
              r.status.equals(SyncState.failed) | r.status.equals(SyncState.conflict)))
        .write(
      SyncQueueCompanion(
        status: const Value(SyncState.pending),
        attempts: const Value(0),
        nextAttemptAt: const Value(null),
        lastError: const Value(null),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  Future<void> retry(String packageId) {
    return (update(syncQueue)..where((r) => r.packageId.equals(packageId))).write(
      SyncQueueCompanion(
        status: const Value(SyncState.pending),
        attempts: const Value(0),
        nextAttemptAt: const Value(null),
        lastError: const Value(null),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  // --- events --------------------------------------------------------------

  Future<List<LocalEvent>> unsyncedEvents() {
    return (select(localEvents)..where((e) => e.synced.equals(false))).get();
  }

  Future<void> markEventsSynced(List<String> ids) {
    return (update(localEvents)..where((e) => e.id.isIn(ids)))
        .write(const LocalEventsCompanion(synced: Value(true)));
  }

  // --- reads for providers -------------------------------------------------

  Future<int> countByStatus(String status) async {
    final countExp = syncQueue.packageId.count();
    final n = await (selectOnly(syncQueue)
          ..addColumns([countExp])
          ..where(syncQueue.status.equals(status)))
        .map((r) => r.read(countExp) ?? 0)
        .getSingle();
    return n;
  }

  /// The oldest unsynced (pending/failed/conflict/syncing) record's creation
  /// time, for the "> 4 h unsynced" warning. Null when nothing is unsynced.
  Future<DateTime?> oldestUnsyncedAt() async {
    final q = select(localPackages).join([
      innerJoin(syncQueue, syncQueue.packageId.equalsExp(localPackages.id)),
    ])
      ..where(syncQueue.status.equals(SyncState.synced).not())
      ..orderBy([OrderingTerm.asc(localPackages.createdAt)])
      ..limit(1);
    final row = await q.getSingleOrNull();
    return row?.readTable(localPackages).createdAt;
  }

  /// Total bytes of photos not yet uploaded, for the 500 MB storage warning.
  Future<int> pendingPhotoBytes() async {
    final sumExp = localPhotos.bytes.sum();
    final n = await (selectOnly(localPhotos)
          ..addColumns([sumExp])
          ..where(localPhotos.uploaded.equals(false)))
        .map((r) => r.read(sumExp) ?? 0)
        .getSingle();
    return n;
  }

  /// Reactive stream of all sync records, for the banner/queue counts.
  Stream<List<SyncQueueData>> watchQueue() => select(syncQueue).watch();

  /// Reactive queue rows joined with each package's owner, for the Sync Queue
  /// screen ("waiting for <name>" when owned by another user, PRD §3).
  Stream<List<QueueRow>> watchQueueDetailed() {
    final q = select(syncQueue).join([
      innerJoin(localPackages, localPackages.id.equalsExp(syncQueue.packageId)),
    ]);
    return q.watch().map((rows) {
      return rows.map((r) {
        final s = r.readTable(syncQueue);
        final p = r.readTable(localPackages);
        return QueueRow(
          packageId: s.packageId,
          status: s.status,
          lastError: s.lastError,
          ownerUserId: p.measuredByUserId,
          ownerName: p.measuredByName,
          awb: p.awb,
          provisionalNumber: p.provisionalNumber,
          serverNumber: p.serverPackageNumber,
        );
      }).toList();
    });
  }

  Future<bool> hasUnsynced() async {
    final pending = await countByStatus(SyncState.pending);
    final failed = await countByStatus(SyncState.failed);
    final conflict = await countByStatus(SyncState.conflict);
    final syncing = await countByStatus(SyncState.syncing);
    return pending + failed + conflict + syncing > 0;
  }

  /// Wipe all local data (logout once everything is synced, PRD §10 rule 7).
  Future<void> wipe() {
    return transaction(() async {
      await delete(syncQueue).go();
      await delete(localPhotos).go();
      await delete(localPackages).go();
      await delete(localEvents).go();
      await delete(localShipments).go();
    });
  }

  Future<int> _attempts(String packageId) async {
    final r = await (select(syncQueue)..where((s) => s.packageId.equals(packageId)))
        .getSingleOrNull();
    return r?.attempts ?? 0;
  }
}

/// Open the on-disk database with SQLCipher, keyed by [key]. The key is applied
/// via `PRAGMA key` before any other statement (SQLCipher requirement).
///
/// The loader is pointed at the SQLCipher build (bundled by
/// sqlcipher_flutter_libs). We use the same-isolate [NativeDatabase] rather than
/// the background variant so the `open` overrides below are in effect when the
/// connection is created.
LazyDatabase _openEncrypted(String key) {
  return LazyDatabase(() async {
    if (Platform.isAndroid) {
      await applyWorkaroundToOpenSqlCipherOnOldAndroidVersions();
      open.overrideFor(OperatingSystem.android, openCipherOnAndroid);
    }
    if (Platform.isIOS || Platform.isMacOS) {
      // The SQLCipher pod is statically linked into the process.
      open.overrideFor(OperatingSystem.iOS, DynamicLibrary.process);
      open.overrideFor(OperatingSystem.macOS, DynamicLibrary.process);
    }

    final dir = await getApplicationDocumentsDirectory();
    final file = File(p.join(dir.path, 'measurex.db'));

    return NativeDatabase(
      file,
      setup: (raw) {
        // Key first — SQLCipher requires it before any other statement.
        raw.execute("PRAGMA key = '${key.replaceAll("'", "''")}';");
      },
    );
  });
}
