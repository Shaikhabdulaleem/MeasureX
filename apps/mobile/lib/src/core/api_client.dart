import 'dart:convert';
import 'package:http/http.dart' as http;

/// API base URL. Override per environment with:
///   --dart-define=API_URL=http://<your-pc-ip>:3000/api/v1
/// Default targets the Android emulator's host loopback (10.0.2.2).
const String kApiUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://10.0.2.2:3000/api/v1',
);

class ApiException implements Exception {
  ApiException(this.statusCode, this.code, this.message);
  final int statusCode;
  final String code;
  final String message;
}

class AuthUser {
  AuthUser({
    required this.id,
    required this.employeeId,
    required this.name,
    required this.role,
    required this.mustChangePassword,
  });

  final String id;
  final String employeeId;
  final String name;
  final String role;
  final bool mustChangePassword;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id'] as String,
      employeeId: json['employeeId'] as String,
      name: json['name'] as String,
      role: json['role'] as String,
      mustChangePassword: json['mustChangePassword'] as bool? ?? false,
    );
  }
}

class TokenPair {
  TokenPair({
    required this.accessToken,
    required this.refreshToken,
    required this.mustChangePassword,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final bool mustChangePassword;
  final AuthUser user;

  factory TokenPair.fromJson(Map<String, dynamic> json) {
    return TokenPair(
      accessToken: json['accessToken'] as String,
      refreshToken: json['refreshToken'] as String,
      mustChangePassword: json['mustChangePassword'] as bool? ?? false,
      user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
    );
  }
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Uri _uri(String path) => Uri.parse('$kApiUrl$path');

  Future<TokenPair> login(String employeeId, String password) async {
    final res = await _client.post(
      _uri('/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'employeeId': employeeId, 'password': password}),
    );
    if (res.statusCode != 200) throw _error(res);
    return TokenPair.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<void> changePassword(
    String accessToken,
    String currentPassword,
    String newPassword,
  ) async {
    final res = await _client.post(
      _uri('/auth/change-password'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({
        'currentPassword': currentPassword,
        'newPassword': newPassword,
      }),
    );
    if (res.statusCode != 204) throw _error(res);
  }

  Future<void> logout(String accessToken, String refreshToken) async {
    try {
      await _client.post(
        _uri('/auth/logout'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $accessToken',
        },
        body: jsonEncode({'refreshToken': refreshToken}),
      );
    } catch (_) {
      // Best-effort; local session is cleared regardless.
    }
  }

  // --- M1: scan & capture --------------------------------------------------

  Map<String, String> _authHeaders(String token, {bool json = true}) => {
        if (json) 'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      };

  /// Effective configuration (divisor, step, AWB regex, dimension limits).
  Future<EffectiveConfig> getConfig(String token) async {
    final res = await _client.get(_uri('/devices/me/config'), headers: _authHeaders(token));
    if (res.statusCode != 200) throw _error(res);
    return EffectiveConfig.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Cross-device history check for an AWB.
  Future<AwbLookupResult> lookupAwb(String token, String awb) async {
    final res = await _client.get(_uri('/awb/$awb/lookup'), headers: _authHeaders(token));
    if (res.statusCode != 200) throw _error(res);
    return AwbLookupResult.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Create a package (idempotent). [id] and [idempotencyKey] are client-generated.
  Future<PackageModel> createPackage(
    String token,
    String awb, {
    required String id,
    required int lengthMm,
    required int widthMm,
    required int heightMm,
    required String confirmedAt,
    required String idempotencyKey,
    String method = 'manual',
    String weightSource = 'none',
    String? deviceId,
  }) async {
    final res = await _client.post(
      _uri('/shipments/$awb/packages'),
      headers: {..._authHeaders(token), 'Idempotency-Key': idempotencyKey},
      body: jsonEncode({
        'id': id,
        'lengthMm': lengthMm,
        'widthMm': widthMm,
        'heightMm': heightMm,
        'method': method,
        'weightSource': weightSource,
        'confirmedAt': confirmedAt,
        if (deviceId != null) 'deviceId': deviceId,
      }),
    );
    if (res.statusCode != 201 && res.statusCode != 200) throw _error(res);
    return PackageModel.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Request a signed upload target for a package photo.
  Future<PhotoUploadTarget> requestPhotoUpload(
    String token,
    String packageId, {
    required String contentType,
    int? bytes,
    int? width,
    int? height,
  }) async {
    final res = await _client.post(
      _uri('/packages/$packageId/photos'),
      headers: _authHeaders(token),
      body: jsonEncode({
        'kind': 'raw',
        'contentType': contentType,
        if (bytes != null) 'bytes': bytes,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
      }),
    );
    if (res.statusCode != 201) throw _error(res);
    return PhotoUploadTarget.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Upload the JPEG bytes directly to the signed URL (bypasses the API).
  Future<void> uploadPhotoBytes(PhotoUploadTarget target, List<int> bytes) async {
    final res = await _client.put(
      Uri.parse(target.uploadUrl),
      headers: target.headers,
      body: bytes,
    );
    if (res.statusCode != 200 && res.statusCode != 204) {
      throw ApiException(res.statusCode, 'UPLOAD_FAILED', 'Photo upload failed');
    }
  }

  Future<ShipmentModel> completeShipment(String token, String awb) async {
    final res = await _client.post(_uri('/shipments/$awb/complete'), headers: _authHeaders(token));
    if (res.statusCode != 200) throw _error(res);
    return ShipmentModel.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<ShipmentDetail> getShipment(String token, String awb) async {
    final res = await _client.get(_uri('/shipments/$awb'), headers: _authHeaders(token));
    if (res.statusCode != 200) throw _error(res);
    return ShipmentDetail.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Own measurements (optionally since a date). Server scopes to the caller.
  Future<List<ShipmentModel>> listShipments(
    String token, {
    String? employeeId,
    String? dateFrom,
  }) async {
    final params = <String, String>{
      if (employeeId != null) 'employeeId': employeeId,
      if (dateFrom != null) 'dateFrom': dateFrom,
      'limit': '100',
    };
    final res = await _client.get(
      _uri('/shipments').replace(queryParameters: params),
      headers: _authHeaders(token),
    );
    if (res.statusCode != 200) throw _error(res);
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return (body['items'] as List<dynamic>)
        .map((e) => ShipmentModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Labour "Flag for Team Leader" on a completed shipment.
  Future<void> flagShipment(String token, String shipmentId, {String? note}) async {
    final res = await _client.post(
      _uri('/flags'),
      headers: _authHeaders(token),
      body: jsonEncode({'shipmentId': shipmentId, if (note != null) 'note': note}),
    );
    if (res.statusCode != 201) throw _error(res);
  }

  /// Team Leader / Admin request a remeasurement on a completed shipment.
  Future<void> requestRemeasure(
    String token,
    String shipmentId,
    List<String> packageIds,
    String reason, {
    String? note,
  }) async {
    final res = await _client.post(
      _uri('/remeasurements'),
      headers: _authHeaders(token),
      body: jsonEncode({
        'shipmentId': shipmentId,
        'packageIds': packageIds,
        'reason': reason,
        if (note != null) 'note': note,
      }),
    );
    if (res.statusCode != 201) throw _error(res);
  }

  ApiException _error(http.Response res) {
    String code = 'ERROR';
    String message = 'Request failed';
    try {
      final body = jsonDecode(res.body) as Map<String, dynamic>;
      code = body['code'] as String? ?? code;
      message = body['message'] as String? ?? message;
    } catch (_) {
      // keep defaults
    }
    return ApiException(res.statusCode, code, message);
  }
}

// --- M1 models -------------------------------------------------------------

class EffectiveConfig {
  EffectiveConfig({
    required this.awbRegex,
    required this.volumetricDivisor,
    required this.chargeableStepKg,
    required this.weightRequired,
    required this.minDimensionCm,
    required this.maxDimensionCm,
  });

  final String awbRegex;
  final int volumetricDivisor;
  final double chargeableStepKg;
  final bool weightRequired;
  final int minDimensionCm;
  final int maxDimensionCm;

  factory EffectiveConfig.fromJson(Map<String, dynamic> json) => EffectiveConfig(
        awbRegex: json['awbRegex'] as String? ?? r'^AY\d{11}$',
        volumetricDivisor: (json['volumetricDivisor'] as num?)?.toInt() ?? 5000,
        chargeableStepKg: (json['chargeableStepKg'] as num?)?.toDouble() ?? 0.5,
        weightRequired: json['weightRequired'] as bool? ?? false,
        minDimensionCm: (json['minDimensionCm'] as num?)?.toInt() ?? 1,
        maxDimensionCm: (json['maxDimensionCm'] as num?)?.toInt() ?? 300,
      );
}

class MeasurementVersionModel {
  MeasurementVersionModel({
    required this.lengthMm,
    required this.widthMm,
    required this.heightMm,
    required this.billingLCm,
    required this.billingWCm,
    required this.billingHCm,
    required this.cbm,
    required this.volumetricG,
    required this.chargeableG,
    required this.divisorUsed,
    this.actualWeightG,
    this.method,
    this.confidence,
  });

  final int lengthMm;
  final int widthMm;
  final int heightMm;
  final int billingLCm;
  final int billingWCm;
  final int billingHCm;
  final double cbm;
  final int volumetricG;
  final int chargeableG;
  final int divisorUsed;
  final int? actualWeightG;
  final String? method;
  final String? confidence;

  factory MeasurementVersionModel.fromJson(Map<String, dynamic> json) =>
      MeasurementVersionModel(
        lengthMm: (json['lengthMm'] as num).toInt(),
        widthMm: (json['widthMm'] as num).toInt(),
        heightMm: (json['heightMm'] as num).toInt(),
        billingLCm: (json['billingLCm'] as num).toInt(),
        billingWCm: (json['billingWCm'] as num).toInt(),
        billingHCm: (json['billingHCm'] as num).toInt(),
        cbm: (json['cbm'] as num).toDouble(),
        volumetricG: (json['volumetricG'] as num).toInt(),
        chargeableG: (json['chargeableG'] as num).toInt(),
        divisorUsed: (json['divisorUsed'] as num).toInt(),
        actualWeightG: (json['actualWeightG'] as num?)?.toInt(),
        method: json['method'] as String?,
        confidence: json['confidence'] as String?,
      );
}

class PackageModel {
  PackageModel({
    required this.id,
    required this.shipmentId,
    required this.status,
    this.packageNumber,
    this.currentVersion,
  });

  final String id;
  final String shipmentId;
  final String status;
  final int? packageNumber;
  final MeasurementVersionModel? currentVersion;

  factory PackageModel.fromJson(Map<String, dynamic> json) => PackageModel(
        id: json['id'] as String,
        shipmentId: json['shipmentId'] as String,
        status: json['status'] as String? ?? 'active',
        packageNumber: (json['packageNumber'] as num?)?.toInt(),
        currentVersion: json['currentVersion'] == null
            ? null
            : MeasurementVersionModel.fromJson(
                json['currentVersion'] as Map<String, dynamic>),
      );
}

class ShipmentTotals {
  ShipmentTotals({
    required this.pieces,
    required this.cbm,
    required this.actualG,
    required this.volumetricG,
    required this.chargeableG,
  });

  final int pieces;
  final double cbm;
  final int actualG;
  final int volumetricG;
  final int chargeableG;

  factory ShipmentTotals.fromJson(Map<String, dynamic> json) => ShipmentTotals(
        pieces: (json['pieces'] as num?)?.toInt() ?? 0,
        cbm: (json['cbm'] as num?)?.toDouble() ?? 0,
        actualG: (json['actualG'] as num?)?.toInt() ?? 0,
        volumetricG: (json['volumetricG'] as num?)?.toInt() ?? 0,
        chargeableG: (json['chargeableG'] as num?)?.toInt() ?? 0,
      );
}

class ShipmentModel {
  ShipmentModel({
    required this.id,
    required this.awb,
    required this.status,
    required this.totals,
    this.completedAt,
    this.createdAt,
  });

  final String id;
  final String awb;
  final String status;
  final ShipmentTotals totals;
  final String? completedAt;
  final String? createdAt;

  factory ShipmentModel.fromJson(Map<String, dynamic> json) => ShipmentModel(
        id: json['id'] as String,
        awb: json['awb'] as String,
        status: json['status'] as String,
        totals: ShipmentTotals.fromJson(
            (json['totals'] as Map<String, dynamic>?) ?? const {}),
        completedAt: json['completedAt'] as String?,
        createdAt: json['createdAt'] as String?,
      );
}

class ShipmentDetail extends ShipmentModel {
  ShipmentDetail({
    required super.id,
    required super.awb,
    required super.status,
    required super.totals,
    required this.packages,
    super.completedAt,
    super.createdAt,
  });

  final List<PackageModel> packages;

  factory ShipmentDetail.fromJson(Map<String, dynamic> json) => ShipmentDetail(
        id: json['id'] as String,
        awb: json['awb'] as String,
        status: json['status'] as String,
        totals: ShipmentTotals.fromJson(
            (json['totals'] as Map<String, dynamic>?) ?? const {}),
        completedAt: json['completedAt'] as String?,
        createdAt: json['createdAt'] as String?,
        packages: ((json['packages'] as List<dynamic>?) ?? [])
            .map((e) => PackageModel.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class AwbLookupResult {
  AwbLookupResult({
    required this.awb,
    required this.found,
    required this.nextPackageNumber,
    this.shipment,
  });

  final String awb;
  final bool found;
  final int nextPackageNumber;
  final ShipmentDetail? shipment;

  factory AwbLookupResult.fromJson(Map<String, dynamic> json) => AwbLookupResult(
        awb: json['awb'] as String,
        found: json['found'] as bool? ?? false,
        nextPackageNumber: (json['nextPackageNumber'] as num?)?.toInt() ?? 1,
        shipment: json['shipment'] == null
            ? null
            : ShipmentDetail.fromJson(json['shipment'] as Map<String, dynamic>),
      );
}

class PhotoUploadTarget {
  PhotoUploadTarget({
    required this.photoId,
    required this.uploadUrl,
    required this.method,
    required this.headers,
  });

  final String photoId;
  final String uploadUrl;
  final String method;
  final Map<String, String> headers;

  factory PhotoUploadTarget.fromJson(Map<String, dynamic> json) => PhotoUploadTarget(
        photoId: json['photoId'] as String,
        uploadUrl: json['uploadUrl'] as String,
        method: json['method'] as String? ?? 'PUT',
        headers: ((json['headers'] as Map<String, dynamic>?) ?? {})
            .map((k, v) => MapEntry(k, v.toString())),
      );
}
