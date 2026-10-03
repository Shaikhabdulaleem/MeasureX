import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The material needed to restore or re-authenticate a session, including
/// offline (PRD §3, §10 rule 6). Everything lives in platform secure storage.
class StoredSession {
  const StoredSession({
    required this.accessToken,
    required this.refreshToken,
    required this.userJson,
    required this.employeeId,
    required this.passwordHash,
    required this.offlineUntil,
  });

  final String accessToken;
  final String refreshToken;

  /// The authenticated user as JSON (to rebuild AuthUser offline).
  final String userJson;
  final String employeeId;

  /// A bcrypt hash of the password, to verify an offline login.
  final String passwordHash;

  /// Until when offline use is allowed (12 h shift + 12 h grace).
  final DateTime offlineUntil;
}

/// Persists auth tokens and the offline-login material in secure storage
/// (Keychain / Keystore).
class SessionStore {
  SessionStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _accessKey = 'measurex.accessToken';
  static const _refreshKey = 'measurex.refreshToken';
  static const _userKey = 'measurex.user';
  static const _employeeKey = 'measurex.employeeId';
  static const _pwHashKey = 'measurex.pwHash';
  static const _offlineUntilKey = 'measurex.offlineUntil';

  Future<void> save(StoredSession s) async {
    await _storage.write(key: _accessKey, value: s.accessToken);
    await _storage.write(key: _refreshKey, value: s.refreshToken);
    await _storage.write(key: _userKey, value: s.userJson);
    await _storage.write(key: _employeeKey, value: s.employeeId);
    await _storage.write(key: _pwHashKey, value: s.passwordHash);
    await _storage.write(key: _offlineUntilKey, value: s.offlineUntil.toUtc().toIso8601String());
  }

  Future<StoredSession?> read() async {
    final access = await _storage.read(key: _accessKey);
    final refresh = await _storage.read(key: _refreshKey);
    final user = await _storage.read(key: _userKey);
    final employeeId = await _storage.read(key: _employeeKey);
    final pwHash = await _storage.read(key: _pwHashKey);
    final offlineUntilRaw = await _storage.read(key: _offlineUntilKey);
    if (access == null ||
        refresh == null ||
        user == null ||
        employeeId == null ||
        pwHash == null ||
        offlineUntilRaw == null) {
      return null;
    }
    final offlineUntil = DateTime.tryParse(offlineUntilRaw);
    if (offlineUntil == null) return null;
    return StoredSession(
      accessToken: access,
      refreshToken: refresh,
      userJson: user,
      employeeId: employeeId,
      passwordHash: pwHash,
      offlineUntil: offlineUntil,
    );
  }

  Future<String?> readAccessToken() => _storage.read(key: _accessKey);
  Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
    await _storage.delete(key: _userKey);
    await _storage.delete(key: _employeeKey);
    await _storage.delete(key: _pwHashKey);
    await _storage.delete(key: _offlineUntilKey);
  }
}
