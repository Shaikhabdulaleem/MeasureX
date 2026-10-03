import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app_database.dart';
import 'db_key.dart';

/// Secure-storage-backed SQLCipher key manager.
final dbKeyStoreProvider = Provider<DbKeyStore>((ref) => DbKeyStore());

/// The encrypted local database. Overridden in main() with the real instance
/// (opened with the SQLCipher key); unoverridden use is a programming error.
final appDatabaseProvider = Provider<AppDatabase>((ref) {
  throw UnimplementedError('appDatabaseProvider must be overridden in main()');
});
