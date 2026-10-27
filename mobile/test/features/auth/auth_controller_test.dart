import 'package:chordsync/features/auth/application/auth_controller.dart';
import 'package:chordsync/features/auth/data/auth_token_store.dart';
import 'package:chordsync/features/auth/data/cognito_api.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_cognito.dart';

void main() {
  late FakeCognito api;
  late MemoryAuthTokenStore store;
  var now = DateTime.utc(2026, 1, 1, 0, 10);
  late AuthController controller;

  setUp(() {
    api = FakeCognito();
    store = MemoryAuthTokenStore();
    now = DateTime.utc(2026, 1, 1, 0, 10);
    controller = AuthController(api: api, store: store, clock: () => now);
  });

  test(
    'starts signed out when nothing is saved, signed in when something is',
    () async {
      await controller.restore();
      expect(controller.status, AuthStatus.signedOut);

      store.tokens = api.tokens('kim@example.com');
      final second = AuthController(api: api, store: store, clock: () => now);
      await second.restore();
      expect(second.isSignedIn, isTrue);
      expect(second.email, 'kim@example.com');
    },
  );

  test(
    'create account: a code is sent, then typing it signs the person in',
    () async {
      await controller.restore();

      expect(await controller.beginSignUp('  Kim@Example.COM '), isTrue);
      expect(controller.waitingForCode, isTrue);
      expect(controller.pendingEmail, 'kim@example.com');
      expect(await controller.submitCode('123456'), isTrue);

      expect(controller.isSignedIn, isTrue);
      expect(controller.waitingForCode, isFalse);
      expect(store.tokens?.email, 'kim@example.com');
      expect(api.calls, ['signUp:kim@example.com', 'confirm:123456']);
    },
  );

  test(
    'when Cognito does not sign in after confirming, a second code is asked for',
    () async {
      api.autoSignIn = false;
      await controller.restore();
      await controller.beginSignUp('kim@example.com');

      expect(await controller.submitCode('123456'), isFalse);
      expect(controller.isSignedIn, isFalse);
      expect(controller.waitingForCode, isTrue); // a new code is on its way
      expect(controller.failure, isNull);

      expect(await controller.submitCode('654321'), isTrue);
      expect(api.calls, [
        'signUp:kim@example.com',
        'confirm:123456',
        'startSignIn:kim@example.com',
        'verify:654321',
      ]);
    },
  );

  test('log in: a code is sent, then typing it signs the person in', () async {
    await controller.restore();
    await controller.beginLogIn('kim@example.com');

    expect(await controller.submitCode('111222'), isTrue);
    expect(controller.isSignedIn, isTrue);
    expect(api.calls, ['startSignIn:kim@example.com', 'verify:111222']);
  });

  test('a bad email is refused before anything is sent', () async {
    for (final bad in ['', 'kim', 'kim@', 'kim@example', 'a b@c.d']) {
      expect(await controller.beginLogIn(bad), isFalse);
      expect(controller.failure, AuthFailure.invalidEmail);
    }
    expect(api.calls, isEmpty);
  });

  test(
    'a code that is not six digits is refused without asking Cognito',
    () async {
      await controller.beginLogIn('kim@example.com');
      api.calls.clear();

      for (final bad in ['', '12345', '1234567', 'abcdef', '12 456']) {
        expect(await controller.submitCode(bad), isFalse);
        expect(controller.failure, AuthFailure.wrongCode);
      }
      expect(api.calls, isEmpty);
    },
  );

  test('a wrong code keeps the person on the code step and says why', () async {
    await controller.beginLogIn('kim@example.com');
    api.failNext = AuthFailure.wrongCode;

    expect(await controller.submitCode('000000'), isFalse);
    expect(controller.failure, AuthFailure.wrongCode);
    expect(controller.waitingForCode, isTrue);
    expect(controller.isSignedIn, isFalse);

    expect(await controller.submitCode('123456'), isTrue); // the next try works
    expect(controller.failure, isNull);
  });

  test('an email that already has an account is reported on sign-up', () async {
    api.failNext = AuthFailure.accountExists;

    expect(await controller.beginSignUp('kim@example.com'), isFalse);
    expect(controller.failure, AuthFailure.accountExists);
    expect(controller.waitingForCode, isFalse);
  });

  test('resend sends the same kind of code again', () async {
    await controller.beginSignUp('kim@example.com');
    expect(await controller.resendCode(), isTrue);
    expect(api.calls, ['signUp:kim@example.com', 'signUp:kim@example.com']);

    controller.cancel();
    expect(controller.waitingForCode, isFalse);
    expect(await controller.resendCode(), isFalse); // nothing to resend
    await controller.beginLogIn('kim@example.com');
    await controller.resendCode();
    expect(api.calls.last, 'startSignIn:kim@example.com');
  });

  test('the access token is used as it is while it has time left', () async {
    store.tokens = api.tokens('kim@example.com'); // expires 01:00, now 00:10
    await controller.restore();

    expect(await controller.accessToken(), 'access-1');
    expect(api.refreshCount, 0);
  });

  test(
    'a token that is nearly out of time is renewed once, even for many requests',
    () async {
      store.tokens = api.tokens('kim@example.com');
      await controller.restore();
      now = DateTime.utc(2026, 1, 1, 0, 59); // inside the two-minute margin

      final tokens = await Future.wait([
        controller.accessToken(),
        controller.accessToken(),
        controller.accessToken(),
      ]);

      expect(tokens, everyElement('access-2'));
      expect(api.refreshCount, 1);
      expect(store.tokens?.accessToken, 'access-2');
      expect(store.tokens?.refreshToken, 'refresh-1');
    },
  );

  test('a lost connection while renewing does not sign anyone out', () async {
    store.tokens = api.tokens('kim@example.com');
    await controller.restore();
    now = DateTime.utc(2026, 1, 1, 0, 59);
    api.refreshFailure = AuthFailure.network;

    expect(
      await controller.accessToken(),
      'access-1',
    ); // still valid for a minute
    expect(controller.isSignedIn, isTrue);

    now = DateTime.utc(2026, 1, 1, 1, 5); // now it has really run out
    expect(await controller.accessToken(), isNull);
    expect(controller.isSignedIn, isTrue);
  });

  test('a refused renewal ends the session and clears the phone', () async {
    store.tokens = api.tokens('kim@example.com');
    await controller.restore();
    now = DateTime.utc(2026, 1, 1, 0, 59);
    api.refreshFailure = AuthFailure.sessionEnded;

    expect(await controller.accessToken(), isNull);
    expect(controller.status, AuthStatus.signedOut);
    expect(store.tokens, isNull);
  });

  test('sign out clears the phone first, then tells the server', () async {
    store.tokens = api.tokens('kim@example.com');
    await controller.restore();

    await controller.signOut();

    expect(controller.status, AuthStatus.signedOut);
    expect(store.tokens, isNull);
    expect(await controller.accessToken(), isNull);
    expect(api.calls, ['revoke']);
  });

  test('nobody signed in means no token', () async {
    await controller.restore();
    expect(await controller.accessToken(), isNull);
  });
}
