import 'dart:async';
import 'dart:io';

import '../../core/api_client.dart';
import '../../core/db/app_database.dart';
import 'backoff.dart';

/// Reads a photo's bytes from disk; injectable so tests avoid real file IO.
typedef PhotoReader = Future<List<int>> Function(String path);

/// Checks a photo file exists; injectable so tests can simulate a missing file.
typedef PhotoExistsChecker = Future<bool> Function(String path);

/// Outcome of attempting to store a package's photo.
enum _PhotoOutcome { ok, missing, failed }

/// Drives offline → server sync (PRD §8, §10). Package data goes first via
/// /sync/batch, then each package's photo; a package is only `synced` once its
/// photo is stored (rule 4). Only the logged-in user's own records are uploaded
/// (PRD §3 shared phones). Failures back off exponentially and auto-retry; a
/// manual Retry resets the backoff. Runs are serialised (never overlapping).
class SyncEngine {
  SyncEngine({
    required AppDatabase db,
    required ApiClient api,
    required String? Function() token,
    required String? Function() userId,
    PhotoReader? photoReader,
    PhotoExistsChecker? photoExists,
  })  : _db = db,
        _api = api,
        _token = token,
        _userId = userId,
        _readPhoto = photoReader ?? ((path) => File(path).readAsBytes()),
        _photoExists = photoExists ?? ((path) => File(path).exists());

  final AppDatabase _db;
  final ApiClient _api;
  final String? Function() _token;
  final String? Function() _userId;
  final PhotoReader _readPhoto;
  final PhotoExistsChecker _photoExists;

  static const _batchLimit = 50;

  Timer? _timer;
  bool _running = false;

  /// Start the periodic pump (every 60 s while anything is pending, PRD §10
  /// rule 5). Call [runNow] on reconnect for an immediate flush.
  void start() {
    _timer ??= Timer.periodic(const Duration(seconds: 60), (_) => runNow());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> retryAll() async {
    await _db.retryAll();
    await runOnce();
  }

  /// Manually retry a single record (resets its backoff) and run now.
  Future<void> retry(String packageId) async {
    await _db.retry(packageId);
    await runOnce();
  }

  void runNow() {
    // Fire and forget; overlapping runs are guarded by [_running].
    unawaited(runOnce());
  }

  /// One sync pass. Safe to call concurrently (re-entrant calls return early).
  Future<void> runOnce() async {
    if (_running) return;
    final token = _token();
    final userId = _userId();
    if (token == null || userId == null) return;
    _running = true;
    try {
      await _flushEvents(token);
      await _flushPackages(token, userId);
    } finally {
      _running = false;
    }
  }

  Future<void> _flushPackages(String token, String userId) async {
    final due = await _db.packagesDueForUser(DateTime.now(), userId);
    if (due.isEmpty) return;

    // Group by AWB and chunk to the batch limit.
    final byAwb = <String, List<LocalPackage>>{};
    for (final p in due) {
      byAwb.putIfAbsent(p.awb, () => []).add(p);
    }

    for (final entry in byAwb.entries) {
      for (final chunk in _chunks(entry.value, _batchLimit)) {
        await _syncChunk(token, chunk);
      }
    }
  }

  Future<void> _syncChunk(String token, List<LocalPackage> chunk) async {
    final ids = chunk.map((p) => p.id).toList();
    await _db.markSyncing(ids);

    List<SyncItemResult> results;
    try {
      results = await _api.syncBatch(token, chunk.map(_toJson).toList());
    } catch (e) {
      // Whole batch failed to reach the server — back every item off.
      for (final p in chunk) {
        await _db.markFailed(p.id, e.toString(), await _backoffFor(p.id));
      }
      return;
    }

    final byId = {for (final r in results) r.id: r};
    for (final p in chunk) {
      final r = byId[p.id];
      if (r == null) {
        await _db.markFailed(p.id, 'no result returned', await _backoffFor(p.id));
        continue;
      }
      if (r.status == SyncState.failed) {
        await _db.markFailed(
          p.id,
          r.errorMessage ?? r.errorCode ?? 'failed',
          await _backoffFor(p.id),
        );
        continue;
      }
      // synced | conflict: the package data is on the server. Upload the photo
      // before marking terminal — a package is only done once its photo stored.
      final photo = await _uploadPhoto(token, p.id);
      if (photo == _PhotoOutcome.missing) {
        // The local photo file is gone — never mark synced (PRD §10 rule 4).
        await _db.markFailed(p.id, 'PHOTO_MISSING', await _backoffFor(p.id));
        continue;
      }
      if (photo == _PhotoOutcome.failed) {
        await _db.markFailed(p.id, 'photo upload failed', await _backoffFor(p.id));
        continue;
      }
      if (r.status == SyncState.conflict) {
        await _db.markConflict(p.id, r.packageNumber);
      } else {
        await _db.markSynced(p.id, r.packageNumber);
      }
    }
  }

  Future<_PhotoOutcome> _uploadPhoto(String token, String packageId) async {
    final photo = await _db.photoFor(packageId);
    if (photo == null) return _PhotoOutcome.ok; // nothing to upload
    if (photo.uploaded) return _PhotoOutcome.ok; // already stored

    // A missing local file can never succeed — surface it distinctly.
    if (!await _photoExists(photo.filePath)) return _PhotoOutcome.missing;

    try {
      // Request the upload target once per photo; on retry ask for a fresh URL
      // for the SAME photo id (no orphan rows, PRD §10 rule 5).
      final PhotoUploadTarget target;
      if (photo.photoId == null) {
        target = await _api.requestPhotoUpload(
          token,
          packageId,
          contentType: 'image/jpeg',
          bytes: photo.bytes,
        );
        await _db.setPhotoId(packageId, target.photoId);
      } else {
        target = await _api.refreshPhotoUpload(token, photo.photoId!);
      }
      final bytes = await _readPhoto(photo.filePath);
      await _api.uploadPhotoBytes(target, bytes);
      await _db.markPhotoUploaded(packageId);
      return _PhotoOutcome.ok;
    } catch (_) {
      return _PhotoOutcome.failed;
    }
  }

  Future<void> _flushEvents(String token) async {
    final events = await _db.unsyncedEvents();
    if (events.isEmpty) return;
    for (final chunk in _chunks(events, 200)) {
      try {
        await _api.postEvents(token, chunk.map(_eventToJson).toList());
        await _db.markEventsSynced(chunk.map((e) => e.id).toList());
      } catch (_) {
        break; // offline — try again next pass
      }
    }
  }

  Future<DateTime> _backoffFor(String packageId) async {
    final records = await _db.recordsWithStatus(SyncState.syncing);
    final current = records.where((r) => r.packageId == packageId).toList();
    final attempts = current.isEmpty ? 1 : current.first.attempts + 1;
    return DateTime.now().add(nextBackoff(attempts));
  }

  static Map<String, dynamic> _toJson(LocalPackage p) => {
        'id': p.id,
        'awb': p.awb,
        'provisionalNumber': p.provisionalNumber,
        'lengthMm': p.lengthMm,
        'widthMm': p.widthMm,
        'heightMm': p.heightMm,
        'method': p.method,
        'weightSource': p.weightSource,
        if (p.actualWeightG != null) 'actualWeightG': p.actualWeightG,
        if (p.weightReason != null) 'weightReason': p.weightReason,
        if (p.scaleId != null) 'scaleId': p.scaleId,
        if (p.confidence != null) 'confidence': p.confidence,
        if (p.deviceId != null) 'deviceId': p.deviceId,
        if (p.measuredByUserId != null) 'measuredBy': p.measuredByUserId,
        'confirmedAt': p.confirmedAt.toUtc().toIso8601String(),
      };

  static Map<String, dynamic> _eventToJson(LocalEvent e) => {
        'id': e.id,
        'type': e.type,
        if (e.awb != null) 'awb': e.awb,
        if (e.deviceId != null) 'deviceId': e.deviceId,
        if (e.measuredByUserId != null) 'userId': e.measuredByUserId,
        'occurredAt': e.occurredAt.toUtc().toIso8601String(),
      };

  static Iterable<List<T>> _chunks<T>(List<T> list, int size) sync* {
    for (var i = 0; i < list.length; i += size) {
      yield list.sublist(i, i + size > list.length ? list.length : i + size);
    }
  }
}
