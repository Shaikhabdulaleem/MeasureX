import 'dart:convert';
import 'dart:math';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Manages the SQLCipher encryption key for the local database (PRD §10 rule 7:
/// "Local database encrypted (SQLCipher)"). The 256-bit key is generated once
/// and stored in platform secure storage (Keychain / Keystore); it never leaves
/// the device and is never logged.
class DbKeyStore {
  DbKeyStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _key = 'measurex.dbKey';

  /// Return the existing key, generating and persisting one on first use.
  Future<String> getOrCreate() async {
    final existing = await _storage.read(key: _key);
    if (existing != null && existing.isNotEmpty) return existing;
    final key = _generateKey();
    await _storage.write(key: _key, value: key);
    return key;
  }

  /// Remove the key — only safe once all local data is wiped (logout after sync).
  Future<void> clear() => _storage.delete(key: _key);

  static String _generateKey() {
    final rng = Random.secure();
    final bytes = List<int>.generate(32, (_) => rng.nextInt(256));
    return base64Url.encode(bytes);
  }
}
