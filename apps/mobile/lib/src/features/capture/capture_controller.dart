import 'dart:io';

import 'package:drift/drift.dart' show Value;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../../core/api_client.dart';
import '../../core/db/app_database.dart';
import '../../core/image_util.dart';
import '../auth/auth_controller.dart';
import '../scale/scale_controller.dart';
import '../sync/sync_providers.dart';

const _uuid = Uuid();

/// A package saved locally during this capture session (for the summary screen).
/// Offline the server number is unknown, so the provisional number is shown as
/// "PKG 02*" until sync replaces it (PRD §10 rule 2).
class SavedPackageResult {
  const SavedPackageResult({
    required this.id,
    required this.awb,
    required this.provisionalNumber,
    this.serverNumber,
    this.lengthMm = 0,
    this.widthMm = 0,
    this.heightMm = 0,
    this.actualWeightG,
  });

  final String id;
  final String awb;
  final int provisionalNumber;
  final int? serverNumber;
  final int lengthMm;
  final int widthMm;
  final int heightMm;
  final int? actualWeightG;
}

class CaptureState {
  const CaptureState({
    this.awb,
    this.shipmentId,
    this.nextPackageNumber = 1,
    this.savedPackages = const [],
  });

  final String? awb;
  final String? shipmentId;
  final int nextPackageNumber;
  final List<SavedPackageResult> savedPackages;

  CaptureState copyWith({
    String? awb,
    String? shipmentId,
    int? nextPackageNumber,
    List<SavedPackageResult>? savedPackages,
  }) {
    return CaptureState(
      awb: awb ?? this.awb,
      shipmentId: shipmentId ?? this.shipmentId,
      nextPackageNumber: nextPackageNumber ?? this.nextPackageNumber,
      savedPackages: savedPackages ?? this.savedPackages,
    );
  }
}

final effectiveConfigProvider = FutureProvider<EffectiveConfig>((ref) async {
  final api = ref.read(apiClientProvider);
  final token = ref.read(authControllerProvider).accessToken;
  if (token == null) throw StateError('not authenticated');
  return api.getConfig(token);
});

final captureControllerProvider =
    StateNotifierProvider<CaptureController, CaptureState>((ref) {
  return CaptureController(ref);
});

class CaptureController extends StateNotifier<CaptureState> {
  CaptureController(this._ref) : super(const CaptureState());

  final Ref _ref;

  ApiClient get _api => _ref.read(apiClientProvider);
  AppDatabase get _db => _ref.read(appDatabaseProvider);
  String? get _token => _ref.read(authControllerProvider).accessToken;

  Future<AwbLookupResult> lookup(String awb) {
    final token = _token;
    if (token == null) throw StateError('not authenticated');
    return _api.lookupAwb(token, awb);
  }

  /// Begin (or resume) a capture session for an AWB. Starting a new AWB clears
  /// any captured scale weight so a fresh stable reading is required (PRD §9).
  void startSession(String awb, int nextPackageNumber, {String? shipmentId}) {
    state = CaptureState(
      awb: awb,
      shipmentId: shipmentId,
      nextPackageNumber: nextPackageNumber,
      savedPackages: const [],
    );
    _ref.read(scaleControllerProvider.notifier).consumeStableWeight();
  }

  /// Save a package locally (PRD §10: the phone is the first place every record
  /// is saved). The photo is compressed to a file; the package + photo + a
  /// sync-queue record are written atomically, then the sync engine is nudged.
  /// No network call happens here — it returns immediately with a provisional
  /// number and the engine syncs in the background.
  Future<SavedPackageResult> savePackage({
    required int lengthMm,
    required int widthMm,
    required int heightMm,
    required List<int> photoBytes,
    String weightSource = 'none',
    int? actualWeightG,
    String? scaleId,
    String? weightReason,
    String contentType = 'image/jpeg',
  }) async {
    final awb = state.awb;
    if (awb == null) throw StateError('no active AWB');

    final id = _uuid.v4();
    final idempotencyKey = _uuid.v4();
    final provisionalNumber = await _db.nextProvisionalNumber(awb);
    final deviceId = await _installId();
    final user = _ref.read(authControllerProvider).user;

    // Compress and persist the photo to app-private storage (PRD §6, §10).
    final compressed = compressForUpload(photoBytes);
    final photoPath = await _writePhoto(id, compressed);

    await _db.savePackageForSync(
      awb: awb,
      photoPath: photoPath,
      photoBytes: compressed.length,
      package: LocalPackagesCompanion.insert(
        id: id,
        awb: awb,
        provisionalNumber: provisionalNumber,
        lengthMm: lengthMm,
        widthMm: widthMm,
        heightMm: heightMm,
        idempotencyKey: idempotencyKey,
        confirmedAt: DateTime.now().toUtc(),
        weightSource: Value(weightSource),
        weightReason: Value(weightReason),
        actualWeightG: Value(actualWeightG),
        scaleId: Value(scaleId),
        deviceId: Value(deviceId),
        measuredByUserId: Value(user?.id),
        measuredByName: Value(user?.name),
      ),
    );

    // A stable weight is consumed once per package: clear it so the next
    // package requires a fresh stable reading (PRD §9).
    _ref.read(scaleControllerProvider.notifier).consumeStableWeight();

    // Nudge the engine so it syncs promptly when online.
    _ref.read(syncEngineProvider).runNow();

    final result = SavedPackageResult(
      id: id,
      awb: awb,
      provisionalNumber: provisionalNumber,
      lengthMm: lengthMm,
      widthMm: widthMm,
      heightMm: heightMm,
      actualWeightG: actualWeightG,
    );
    state = state.copyWith(
      nextPackageNumber: provisionalNumber + 1,
      savedPackages: [...state.savedPackages, result],
    );
    return result;
  }

  /// Complete the shipment. Local-first: build the summary from saved packages;
  /// best-effort tell the server when online (ignored offline — the server
  /// auto-completes after idle, and package sync is unaffected).
  Future<ShipmentModel> complete() async {
    final awb = state.awb;
    if (awb == null) throw StateError('no active AWB');

    final token = _token;
    if (token != null) {
      try {
        return await _api.completeShipment(token, awb);
      } catch (_) {
        // Offline or transient — fall through to a local summary.
      }
    }
    return _localSummary(awb);
  }

  ShipmentModel _localSummary(String awb) {
    var actualG = 0;
    for (final p in state.savedPackages) {
      actualG += p.actualWeightG ?? 0;
    }
    // Volumetric/cbm previews are recomputed on the dashboard from the server
    // figures; the offline summary shows the piece count and actual weight.
    return ShipmentModel(
      id: awb,
      awb: awb,
      status: 'completed',
      totals: ShipmentTotals(
        pieces: state.savedPackages.length,
        cbm: 0,
        actualG: actualG,
        volumetricG: 0,
        chargeableG: 0,
      ),
    );
  }

  Future<String> _writePhoto(String id, List<int> bytes) async {
    final dir = await getApplicationDocumentsDirectory();
    final photos = Directory(p.join(dir.path, 'photos'));
    if (!await photos.exists()) await photos.create(recursive: true);
    final file = File(p.join(photos.path, '$id.jpg'));
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }

  Future<String?> _installId() async {
    // Device registration (M5) will supply a stable install id; until then the
    // deviceId is left null, which the server treats as unscoped.
    return null;
  }

  void reset() => state = const CaptureState();
}
