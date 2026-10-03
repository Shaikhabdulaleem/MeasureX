import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import '../../core/api_client.dart';
import '../auth/auth_controller.dart';

const _uuid = Uuid();

/// A package saved during the current capture session (for the summary screen).
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
  final List<PackageModel> savedPackages;

  CaptureState copyWith({
    String? awb,
    String? shipmentId,
    int? nextPackageNumber,
    List<PackageModel>? savedPackages,
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
  String get _token {
    final token = _ref.read(authControllerProvider).accessToken;
    if (token == null) throw StateError('not authenticated');
    return token;
  }

  Future<AwbLookupResult> lookup(String awb) => _api.lookupAwb(_token, awb);

  /// Begin (or resume) a capture session for an AWB.
  void startSession(String awb, int nextPackageNumber, {String? shipmentId}) {
    state = CaptureState(
      awb: awb,
      shipmentId: shipmentId,
      nextPackageNumber: nextPackageNumber,
      savedPackages: const [],
    );
  }

  /// Save a manually-measured package: create it, then upload its photo.
  /// Weight (PRD §9): [weightSource] is `none`, `scale` (with [scaleId]) or
  /// `manual` (Team Leader / Admin, with [weightReason]).
  Future<PackageModel> savePackage({
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

    final pkg = await _api.createPackage(
      _token,
      awb,
      id: id,
      lengthMm: lengthMm,
      widthMm: widthMm,
      heightMm: heightMm,
      weightSource: weightSource,
      actualWeightG: actualWeightG,
      scaleId: scaleId,
      weightReason: weightReason,
      confirmedAt: DateTime.now().toUtc().toIso8601String(),
      idempotencyKey: idempotencyKey,
    );

    // Package data first, then the photo (PRD §10 upload order).
    final target = await _api.requestPhotoUpload(
      _token,
      pkg.id,
      contentType: contentType,
      bytes: photoBytes.length,
    );
    await _api.uploadPhotoBytes(target, photoBytes);

    state = state.copyWith(
      shipmentId: pkg.shipmentId,
      nextPackageNumber: (pkg.packageNumber ?? state.nextPackageNumber) + 1,
      savedPackages: [...state.savedPackages, pkg],
    );
    return pkg;
  }

  Future<ShipmentModel> complete() async {
    final awb = state.awb;
    if (awb == null) throw StateError('no active AWB');
    return _api.completeShipment(_token, awb);
  }

  void reset() => state = const CaptureState();
}
