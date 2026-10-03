import 'package:drift/drift.dart' show Value;
import 'package:flutter_test/flutter_test.dart';
import 'package:measurex/src/core/api_client.dart';
import 'package:measurex/src/core/db/app_database.dart';
import 'package:measurex/src/features/sync/sync_engine.dart';

/// Fake API: records the ids it was asked to sync and returns programmed
/// results; photo upload can be made to fail to exercise the "synced only after
/// photo" rule (PRD §10 rule 4).
class FakeApi extends ApiClient {
  FakeApi();

  List<Map<String, dynamic>> lastBatch = [];
  int batchCalls = 0;
  int requestPhotoCalls = 0;
  int refreshPhotoCalls = 0;
  bool throwOnBatch = false;
  bool failPhoto = false;
  String Function(String id) statusFor = (_) => 'synced';
  int? numberFor = 1;

  @override
  Future<List<SyncItemResult>> syncBatch(String token, List<Map<String, dynamic>> packages) async {
    batchCalls++;
    lastBatch = packages;
    if (throwOnBatch) throw Exception('network down');
    return packages
        .map((p) => SyncItemResult(
              id: p['id'] as String,
              status: statusFor(p['id'] as String),
              packageNumber: numberFor,
            ))
        .toList();
  }

  @override
  Future<PhotoUploadTarget> requestPhotoUpload(String token, String packageId,
      {required String contentType, int? bytes, int? width, int? height}) async {
    requestPhotoCalls++;
    return PhotoUploadTarget(
      photoId: 'photo_$packageId',
      uploadUrl: 'https://example.test/upload',
      method: 'PUT',
      headers: const {},
    );
  }

  @override
  Future<PhotoUploadTarget> refreshPhotoUpload(String token, String photoId) async {
    refreshPhotoCalls++;
    return PhotoUploadTarget(
      photoId: photoId,
      uploadUrl: 'https://example.test/upload-fresh',
      method: 'PUT',
      headers: const {},
    );
  }

  @override
  Future<void> uploadPhotoBytes(PhotoUploadTarget target, List<int> bytes) async {
    if (failPhoto) throw Exception('photo upload failed');
  }

  @override
  Future<void> postEvents(String token, List<Map<String, dynamic>> events) async {}
}

Future<void> seedPackage(
  AppDatabase db,
  String id, {
  String awb = 'AY00000000001',
  String userId = 'u1',
}) {
  return db.savePackageForSync(
    awb: awb,
    photoPath: '/tmp/$id.jpg',
    photoBytes: 1234,
    package: LocalPackagesCompanion.insert(
      id: id,
      awb: awb,
      provisionalNumber: 1,
      lengthMm: 452,
      widthMm: 301,
      heightMm: 204,
      idempotencyKey: 'key_$id',
      confirmedAt: DateTime.utc(2026, 10, 3, 10),
      measuredByUserId: Value(userId),
      measuredByName: const Value('Worker One'),
    ),
  );
}

void main() {
  late AppDatabase db;
  late FakeApi api;
  late SyncEngine engine;
  late bool photoPresent;

  setUp(() {
    db = AppDatabase.memory();
    api = FakeApi();
    photoPresent = true;
    engine = SyncEngine(
      db: db,
      api: api,
      token: () => 'token',
      userId: () => 'u1',
      photoReader: (_) async => [1, 2, 3], // no real file IO
      photoExists: (_) async => photoPresent,
    );
  });

  tearDown(() async => db.close());

  test('pending → synced after data and photo', () async {
    await seedPackage(db, 'p1');
    await engine.runOnce();

    final rows = await db.recordsWithStatus(SyncState.synced);
    expect(rows.map((r) => r.packageId), ['p1']);
    final photo = await db.photoFor('p1');
    expect(photo!.uploaded, isTrue);
    expect(await db.packagesDueForUser(DateTime.now(), 'u1'), isEmpty);
  });

  test('batch failure → failed with backoff scheduled', () async {
    await seedPackage(db, 'p1');
    api.throwOnBatch = true;
    await engine.runOnce();

    final failed = await db.recordsWithStatus(SyncState.failed);
    expect(failed, hasLength(1));
    expect(failed.first.attempts, 1);
    expect(failed.first.nextAttemptAt, isNotNull);
    expect(failed.first.nextAttemptAt!.isAfter(DateTime.now()), isTrue);
  });

  test('synced only after the photo stores, and retry refreshes the URL', () async {
    await seedPackage(db, 'p1');
    api.failPhoto = true;
    await engine.runOnce();

    // Data reached the server, but the photo failed → not synced yet.
    expect(await db.recordsWithStatus(SyncState.synced), isEmpty);
    expect(await db.recordsWithStatus(SyncState.failed), hasLength(1));
    final photo = await db.photoFor('p1');
    expect(photo!.uploaded, isFalse);
    expect(photo.photoId, 'photo_p1'); // id stored on the first attempt

    // Retry with a working upload → a FRESH URL is requested for the same
    // photo id (no new photo row), then it syncs.
    api.failPhoto = false;
    await engine.retryAll();
    expect(await db.recordsWithStatus(SyncState.synced), hasLength(1));
    expect(api.requestPhotoCalls, 1); // only the first attempt created the row
    expect(api.refreshPhotoCalls, 1); // retry refreshed the URL
  });

  test('missing local photo file → failed PHOTO_MISSING, never synced', () async {
    await seedPackage(db, 'p1');
    photoPresent = false;
    await engine.runOnce();

    expect(await db.recordsWithStatus(SyncState.synced), isEmpty);
    final failed = await db.recordsWithStatus(SyncState.failed);
    expect(failed, hasLength(1));
    expect(failed.first.lastError, 'PHOTO_MISSING');
    expect(api.requestPhotoCalls, 0); // never even asked for an upload URL
  });

  test('conflict result is recorded as conflict', () async {
    await seedPackage(db, 'p1');
    api.statusFor = (_) => SyncState.conflict;
    await engine.runOnce();

    expect(await db.recordsWithStatus(SyncState.conflict), hasLength(1));
  });

  test('only uploads the logged-in user\'s own records (shared phones)', () async {
    await seedPackage(db, 'mine', userId: 'u1');
    await seedPackage(db, 'theirs', awb: 'AY00000000002', userId: 'u2');
    await engine.runOnce();

    // Only u1's package was sent and synced; u2's stays pending on the device.
    expect(api.lastBatch.map((p) => p['id']), ['mine']);
    final synced = await db.recordsWithStatus(SyncState.synced);
    expect(synced.map((r) => r.packageId), ['mine']);
    final pending = await db.recordsWithStatus(SyncState.pending);
    expect(pending.map((r) => r.packageId), ['theirs']);
  });

  test('resync does not re-send an already synced package', () async {
    await seedPackage(db, 'p1');
    await engine.runOnce();
    final callsAfterFirst = api.batchCalls;

    await engine.runOnce(); // nothing due
    expect(api.batchCalls, callsAfterFirst);
  });

  test('manual retry resets a failed record to pending', () async {
    await seedPackage(db, 'p1');
    api.throwOnBatch = true;
    await engine.runOnce();
    expect(await db.recordsWithStatus(SyncState.failed), hasLength(1));

    api.throwOnBatch = false;
    await engine.retryAll();
    expect(await db.recordsWithStatus(SyncState.synced), hasLength(1));
    expect(await db.recordsWithStatus(SyncState.failed), isEmpty);
  });
}
