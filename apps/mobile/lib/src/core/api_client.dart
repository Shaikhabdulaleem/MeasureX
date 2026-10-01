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
