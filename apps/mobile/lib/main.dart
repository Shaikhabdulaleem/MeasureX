import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'src/app.dart';
import 'src/core/db/app_database.dart';
import 'src/core/db/db_key.dart';
import 'src/core/db/db_providers.dart';
import 'src/features/auth/auth_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Open the encrypted local database (PRD §10 rule 7) with the SQLCipher key
  // from secure storage, before the app reads any provider that needs it.
  final key = await DbKeyStore().getOrCreate();
  final db = AppDatabase.encrypted(key);

  final container = ProviderContainer(
    overrides: [appDatabaseProvider.overrideWithValue(db)],
  );
  // Restore a session (online window still valid) without a network call.
  await container.read(authControllerProvider.notifier).bootstrap();

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const MeasureXApp(),
    ),
  );
}
