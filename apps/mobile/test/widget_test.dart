import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:measurex/src/app.dart';

void main() {
  testWidgets('starts on the login screen with a sign-in button', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: MeasureXApp()));
    await tester.pump();

    expect(find.byType(MaterialApp), findsOneWidget);
    // English is the default locale in tests.
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Employee ID'), findsOneWidget);
  });
}
