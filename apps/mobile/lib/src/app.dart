import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'l10n/app_localizations.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/login_screen.dart';
import 'features/auth/change_password_screen.dart';
import 'features/home/home_screen.dart';

class MeasureXApp extends StatelessWidget {
  const MeasureXApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MeasureX',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF0F766E),
        useMaterial3: true,
      ),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const _AuthGate(),
    );
  }
}

class _AuthGate extends ConsumerWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(authControllerProvider).status;
    switch (status) {
      case AuthStatus.authenticated:
        return const HomeScreen();
      case AuthStatus.mustChangePassword:
        return const ChangePasswordScreen();
      case AuthStatus.unknown:
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      case AuthStatus.unauthenticated:
        return const LoginScreen();
    }
  }
}
