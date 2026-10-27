import 'package:chordsync/features/auth/application/auth_controller.dart';
import 'package:chordsync/features/auth/data/auth_token_store.dart';
import 'package:chordsync/features/auth/data/cognito_api.dart';
import 'package:chordsync/features/auth/data/profile_store.dart';
import 'package:chordsync/features/auth/data/user_profile.dart';
import 'package:chordsync/features/auth/presentation/account_button.dart';
import 'package:chordsync/features/auth/presentation/auth_gate.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_cognito.dart';

late FakeCognito api;
late MemoryAuthTokenStore tokens;
late MemoryProfileStore profiles;
late AuthController auth;

final _today = DateTime(2026, 10, 27);

Future<void> _open(WidgetTester tester, {bool signedInStart = false}) async {
  api = FakeCognito();
  tokens = MemoryAuthTokenStore(
    signedInStart ? api.tokens('kim@example.com') : null,
  );
  profiles = MemoryProfileStore();
  auth = AuthController(
    api: api,
    store: tokens,
    clock: () => DateTime.utc(2026, 1, 1, 0, 10),
  );
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await auth.restore();
  await tester.pumpWidget(
    MaterialApp(
      home: AuthGate(
        auth: auth,
        profiles: profiles,
        today: () => _today,
        signedIn: const Scaffold(body: Center(child: Text('THE APP'))),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, String text) async {
  await tester.ensureVisible(find.text(text).first);
  await tester.pump();
  await tester.tap(find.text(text).first);
  await tester.pumpAndSettle();
}

/// The text field that sits under a label (the labels are separate widgets).
Finder _fieldBelow(String label) => find
    .descendant(
      of: find
          .ancestor(of: find.text(label), matching: find.byType(Column))
          .first,
      matching: find.byType(TextField),
    )
    .first;

Future<void> _openBirthdayPicker(WidgetTester tester) async {
  await tester.tap(_fieldBelow('Date of birth'));
  await tester.pumpAndSettle();
}

Future<void> _enter(WidgetTester tester, String label, String value) async {
  await tester.enterText(_fieldBelow(label), value);
  await tester.pump();
}

void main() {
  testWidgets('a signed-out person sees the welcome screen, not the app', (
    tester,
  ) async {
    await _open(tester);

    expect(find.text('ChordSync'), findsOneWidget);
    expect(find.text('Your songs. Your practice.'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    expect(find.text('Create account'), findsOneWidget);
    expect(find.text('THE APP'), findsNothing);
  });

  testWidgets('a person who is already signed in goes straight to the app', (
    tester,
  ) async {
    await _open(tester, signedInStart: true);

    expect(find.text('THE APP'), findsOneWidget);
    expect(find.text('Log in'), findsNothing);
  });

  testWidgets('log in: email, then the code, then the app', (tester) async {
    await _open(tester);
    await _tap(tester, 'Log in');

    expect(find.text('Welcome back'), findsOneWidget);
    await _enter(tester, 'Email', 'Kim@Example.com');
    await _tap(tester, 'Send me a code');

    expect(find.text('Check your email'), findsOneWidget);
    expect(find.textContaining('kim@example.com'), findsOneWidget);
    await _enter(tester, 'Your code', '123456'); // the sixth digit signs in
    await tester.pumpAndSettle();

    expect(find.text('THE APP'), findsOneWidget);
    expect(api.calls, ['startSignIn:kim@example.com', 'verify:123456']);
    expect(tokens.tokens?.email, 'kim@example.com');
  });

  testWidgets('a bad email shows a message and sends nothing', (tester) async {
    await _open(tester);
    await _tap(tester, 'Log in');

    await _enter(tester, 'Email', 'not-an-email');
    await _tap(tester, 'Send me a code');

    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(api.calls, isEmpty);
  });

  testWidgets('a wrong code is explained and the person can try again', (
    tester,
  ) async {
    await _open(tester);
    await _tap(tester, 'Log in');
    await _enter(tester, 'Email', 'kim@example.com');
    await _tap(tester, 'Send me a code');
    api.failNext = AuthFailure.wrongCode;

    await _enter(tester, 'Your code', '000000');
    await tester.pumpAndSettle();

    expect(find.textContaining("isn't right"), findsOneWidget);
    expect(find.text('THE APP'), findsNothing);

    await _enter(tester, 'Your code', '123456');
    await tester.pumpAndSettle();
    expect(find.text('THE APP'), findsOneWidget);
  });

  testWidgets('back on the code step returns to the email step', (
    tester,
  ) async {
    await _open(tester);
    await _tap(tester, 'Log in');
    await _enter(tester, 'Email', 'kim@example.com');
    await _tap(tester, 'Send me a code');

    await _tap(tester, 'Use a different email');

    expect(find.text('Welcome back'), findsOneWidget);
    expect(auth.waitingForCode, isFalse);
  });

  testWidgets(
    'create account: name and birthday, taste, level, then email and code',
    (tester) async {
      await _open(tester);
      await _tap(tester, 'Create account');

      // 1 / 4
      expect(find.text('1 / 4'), findsOneWidget);
      expect(find.text("Let's get to know you"), findsOneWidget);
      await _enter(tester, 'Full name', 'Kim Lee');
      await _openBirthdayPicker(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      await _tap(tester, 'Next');

      // 2 / 4
      expect(find.text('2 / 4'), findsOneWidget);
      await _tap(tester, 'Pop');
      await _tap(tester, 'Jazz');
      await _tap(tester, 'Next');

      // 3 / 4
      expect(find.text('3 / 4'), findsOneWidget);
      await _tap(tester, 'Intermediate');
      await _tap(tester, 'Next');

      // 4 / 4
      expect(find.text('4 / 4'), findsOneWidget);
      await _enter(tester, 'Email', 'kim@example.com');
      await _tap(tester, 'Send me a code');
      expect(find.text('Check your email'), findsOneWidget);
      await _enter(tester, 'Your code', '123456');
      await tester.pumpAndSettle();

      expect(find.text('THE APP'), findsOneWidget);
      expect(api.calls, ['signUp:kim@example.com', 'confirm:123456']);
      final saved = profiles.profile!;
      expect(saved.name, 'Kim Lee');
      expect(saved.genres, ['Pop', 'Jazz']);
      expect(saved.experience, GuitarExperience.intermediate);
      expect(
        UserProfile.ageOn(saved.birthDate, _today),
        greaterThanOrEqualTo(13),
      );
    },
  );

  testWidgets('step 1 asks for a name and a birthday before going on', (
    tester,
  ) async {
    await _open(tester);
    await _tap(tester, 'Create account');

    await _tap(tester, 'Next');
    expect(find.text('Tell us your name.'), findsOneWidget);

    await _enter(tester, 'Full name', 'Kim');
    await _tap(tester, 'Next');
    expect(find.text('Choose your date of birth.'), findsOneWidget);
    expect(find.text('2 / 4'), findsNothing);
  });

  testWidgets('the birthday picker does not offer anyone under 13', (
    tester,
  ) async {
    await _open(tester);
    await _tap(tester, 'Create account');
    await _openBirthdayPicker(tester);
    await tester.pumpAndSettle();

    final picker = tester.widget<CalendarDatePicker>(
      find.byType(CalendarDatePicker),
    );
    expect(picker.lastDate, DateTime(2013, 10, 27));
  });

  testWidgets('step 2 needs a choice, or can be skipped', (tester) async {
    await _open(tester);
    await _tap(tester, 'Create account');
    await _enter(tester, 'Full name', 'Kim Lee');
    await _openBirthdayPicker(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await _tap(tester, 'Next');

    await _tap(tester, 'Next'); // nothing chosen yet: stays
    expect(find.text('3 / 4'), findsNothing);
    await _tap(tester, 'Skip for now');
    expect(find.text('3 / 4'), findsOneWidget);
  });

  testWidgets('back goes to the earlier step and keeps what was typed', (
    tester,
  ) async {
    await _open(tester);
    await _tap(tester, 'Create account');
    await _enter(tester, 'Full name', 'Kim Lee');
    await _openBirthdayPicker(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await _tap(tester, 'Next');
    expect(find.text('2 / 4'), findsOneWidget);

    await tester.tap(find.byTooltip('Back'));
    await tester.pumpAndSettle();

    expect(find.text('1 / 4'), findsOneWidget);
    expect(find.text('Kim Lee'), findsOneWidget);
  });

  testWidgets(
    'an email that already has an account says so and offers log in',
    (tester) async {
      await _open(tester);
      await _tap(tester, 'Create account');
      await _enter(tester, 'Full name', 'Kim Lee');
      await _openBirthdayPicker(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      await _tap(tester, 'Next');
      await _tap(tester, 'Skip for now');
      await _tap(tester, 'Complete beginner');
      await _tap(tester, 'Next');
      await _enter(tester, 'Email', 'kim@example.com');
      api.failNext = AuthFailure.accountExists;

      await _tap(tester, 'Send me a code');

      expect(find.textContaining('already has an account'), findsOneWidget);
      await _tap(tester, 'Already have an account? Log in');
      expect(find.text('Welcome back'), findsOneWidget);
    },
  );

  testWidgets('signing out returns to the welcome screen', (tester) async {
    await _open(tester, signedInStart: true);
    expect(find.text('THE APP'), findsOneWidget);

    await auth.signOut();
    await tester.pumpAndSettle();

    expect(find.text('Log in'), findsOneWidget);
    expect(find.text('THE APP'), findsNothing);
  });

  testWidgets('the account button shows who is signed in and logs them out', (
    tester,
  ) async {
    await _open(tester, signedInStart: true);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(child: AccountButton(auth: auth)),
        ),
      ),
    );

    await tester.tap(find.byTooltip('Account'));
    await tester.pumpAndSettle();
    expect(find.text('kim@example.com'), findsOneWidget);

    await tester.tap(find.text('Log out'));
    await tester.pumpAndSettle();

    expect(auth.status, AuthStatus.signedOut);
    expect(tokens.tokens, isNull);
    expect(api.calls, ['revoke']);
  });
}
