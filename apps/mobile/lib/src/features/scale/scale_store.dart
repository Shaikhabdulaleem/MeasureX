import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Remembers the station's chosen scale so the app reconnects automatically
/// (PRD §9: "Pair once per station; the app remembers the station's scale").
class ScaleStore {
  ScaleStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _scaleIdKey = 'measurex.scaleId';

  Future<void> saveScaleId(String scaleId) => _storage.write(key: _scaleIdKey, value: scaleId);
  Future<String?> readScaleId() => _storage.read(key: _scaleIdKey);
  Future<void> clear() => _storage.delete(key: _scaleIdKey);
}
