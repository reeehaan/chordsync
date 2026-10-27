import 'dart:convert';
import 'dart:typed_data';

import 'package:chordsync/features/auth/data/auth_tokens.dart';
import 'package:chordsync/features/auth/data/cognito_api.dart';
import 'package:chordsync/features/auth/data/cognito_config.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

class _Reply {
  const _Reply(this.status, this.body);
  final int status;
  final Map<String, Object?> body;
}

/// Answers each request in turn and records what was sent.
class _Adapter implements HttpClientAdapter {
  _Adapter(this.replies);

  final List<_Reply> replies;
  final targets = <String>[];
  final bodies = <Map<String, Object?>>[];
  final contentTypes = <String?>[];
  DioExceptionType? failWith;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (failWith != null) {
      throw DioException(requestOptions: options, type: failWith!);
    }
    targets.add('${options.headers['X-Amz-Target']}');
    contentTypes.add(options.contentType);
    bodies.add(Map<String, Object?>.from(options.data as Map));
    final reply = replies.removeAt(0);
    return ResponseBody.fromString(
      jsonEncode(reply.body),
      reply.status,
      headers: {
        Headers.contentTypeHeader: ['application/x-amz-json-1.1'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

const _config = CognitoConfig(clientId: 'client123', region: 'ap-southeast-1');
final _now = DateTime.utc(2026, 1, 1, 12);

({DioCognitoApi api, _Adapter adapter}) _make(List<_Reply> replies) {
  final adapter = _Adapter(replies);
  final dio = Dio(
    BaseOptions(baseUrl: _config.endpoint, validateStatus: (_) => true),
  )..httpClientAdapter = adapter;
  return (
    api: DioCognitoApi(config: _config, dio: dio, clock: () => _now),
    adapter: adapter,
  );
}

_Reply _tokens({
  String access = 'A',
  String? refresh = 'R',
  int expires = 3600,
}) => _Reply(200, {
  'AuthenticationResult': {
    'AccessToken': access,
    'RefreshToken': ?refresh,
    'ExpiresIn': expires,
  },
});

void main() {
  test('the endpoint is the https address of the configured region', () {
    expect(
      _config.endpoint,
      'https://cognito-idp.ap-southeast-1.amazonaws.com/',
    );
    expect(const CognitoConfig(clientId: '').isConfigured, isFalse);
    expect(_config.isConfigured, isTrue);
  });

  test('sign up sends the email and no password', () async {
    final t = _make([
      const _Reply(200, {'Session': 'S1', 'UserConfirmed': false}),
    ]);

    final challenge = await t.api.signUp('kim@example.com');

    expect(challenge.session, 'S1');
    expect(t.adapter.targets, ['AWSCognitoIdentityProviderService.SignUp']);
    expect(t.adapter.contentTypes.single, 'application/x-amz-json-1.1');
    final body = t.adapter.bodies.single;
    expect(body['ClientId'], 'client123');
    expect(body['Username'], 'kim@example.com');
    expect(body.containsKey('Password'), isFalse);
    expect(body['UserAttributes'], [
      {'Name': 'email', 'Value': 'kim@example.com'},
    ]);
  });

  test(
    'confirming sign-up signs the person in with the returned session',
    () async {
      final t = _make([
        const _Reply(200, {'Session': 'S2'}),
        _tokens(),
      ]);

      final tokens = await t.api.confirmSignUp(
        challenge: const OtpChallenge(email: 'kim@example.com', session: 'S1'),
        code: '123456',
      );

      expect(tokens?.accessToken, 'A');
      expect(tokens?.refreshToken, 'R');
      expect(tokens?.email, 'kim@example.com');
      expect(tokens?.accessExpiresAt, _now.add(const Duration(hours: 1)));
      expect(t.adapter.targets, [
        'AWSCognitoIdentityProviderService.ConfirmSignUp',
        'AWSCognitoIdentityProviderService.InitiateAuth',
      ]);
      expect(t.adapter.bodies[0]['ConfirmationCode'], '123456');
      expect(t.adapter.bodies[0]['Session'], 'S1');
      expect(t.adapter.bodies[1]['AuthFlow'], 'USER_AUTH');
      expect(t.adapter.bodies[1]['Session'], 'S2');
    },
  );

  test(
    'if the automatic sign-in after confirming fails, it returns null, not an error',
    () async {
      final t = _make([
        const _Reply(200, {'Session': 'S2'}),
        const _Reply(400, {'__type': 'NotAuthorizedException'}),
      ]);

      expect(
        await t.api.confirmSignUp(
          challenge: const OtpChallenge(email: 'kim@example.com', session: ''),
          code: '123456',
        ),
        isNull,
      );
      expect(t.adapter.bodies[0].containsKey('Session'), isFalse);
    },
  );

  test('log in asks for the email code and returns the challenge', () async {
    final t = _make([
      const _Reply(200, {'ChallengeName': 'EMAIL_OTP', 'Session': 'S3'}),
    ]);

    final challenge = await t.api.startSignIn('kim@example.com');

    expect(challenge.session, 'S3');
    final body = t.adapter.bodies.single;
    expect(body['AuthFlow'], 'USER_AUTH');
    expect(body['AuthParameters'], {
      'USERNAME': 'kim@example.com',
      'PREFERRED_CHALLENGE': 'EMAIL_OTP',
    });
  });

  test('log in picks the email code when Cognito offers a choice', () async {
    final t = _make([
      const _Reply(200, {'ChallengeName': 'SELECT_CHALLENGE', 'Session': 'S3'}),
      const _Reply(200, {'ChallengeName': 'EMAIL_OTP', 'Session': 'S4'}),
    ]);

    final challenge = await t.api.startSignIn('kim@example.com');

    expect(challenge.session, 'S4');
    expect(t.adapter.bodies[1]['ChallengeResponses'], {
      'USERNAME': 'kim@example.com',
      'ANSWER': 'EMAIL_OTP',
    });
  });

  test('any other challenge is reported, not guessed at', () async {
    final t = _make([
      const _Reply(200, {'ChallengeName': 'PASSWORD', 'Session': 'S3'}),
    ]);

    await expectLater(
      t.api.startSignIn('kim@example.com'),
      throwsA(
        isA<AuthException>().having(
          (e) => e.failure,
          'failure',
          AuthFailure.unknown,
        ),
      ),
    );
  });

  test('verifying the code returns tokens', () async {
    final t = _make([_tokens(access: 'ACC', refresh: 'REF', expires: 1800)]);

    final tokens = await t.api.verifySignIn(
      challenge: const OtpChallenge(email: 'kim@example.com', session: 'S3'),
      code: '654321',
    );

    expect(tokens.accessToken, 'ACC');
    expect(tokens.refreshToken, 'REF');
    expect(tokens.accessExpiresAt, _now.add(const Duration(minutes: 30)));
    expect(t.adapter.bodies.single['ChallengeResponses'], {
      'USERNAME': 'kim@example.com',
      'EMAIL_OTP_CODE': '654321',
    });
  });

  test('a repeated challenge after a code means the code was wrong', () async {
    final t = _make([
      const _Reply(200, {'ChallengeName': 'EMAIL_OTP', 'Session': 'S5'}),
    ]);

    await expectLater(
      t.api.verifySignIn(
        challenge: const OtpChallenge(email: 'kim@example.com', session: 'S3'),
        code: '000000',
      ),
      throwsA(
        isA<AuthException>().having(
          (e) => e.failure,
          'failure',
          AuthFailure.wrongCode,
        ),
      ),
    );
  });

  test(
    'refreshing keeps the refresh token and replaces the access token',
    () async {
      final t = _make([_tokens(access: 'NEW', refresh: null)]);
      final old = AuthTokens(
        email: 'kim@example.com',
        accessToken: 'OLD',
        refreshToken: 'REF',
        accessExpiresAt: _now,
      );

      final renewed = await t.api.refresh(old);

      expect(renewed.accessToken, 'NEW');
      expect(renewed.refreshToken, 'REF');
      expect(renewed.email, 'kim@example.com');
      expect(t.adapter.bodies.single['AuthFlow'], 'REFRESH_TOKEN_AUTH');
      expect(t.adapter.bodies.single['AuthParameters'], {
        'REFRESH_TOKEN': 'REF',
      });
    },
  );

  test('signing out revokes the refresh token and never throws', () async {
    final t = _make([
      const _Reply(400, {'__type': 'NotAuthorizedException'}),
    ]);
    final tokens = AuthTokens(
      email: 'kim@example.com',
      accessToken: 'A',
      refreshToken: 'REF',
      accessExpiresAt: _now,
    );

    await t.api.revoke(tokens);

    expect(t.adapter.targets, [
      'AWSCognitoIdentityProviderService.RevokeToken',
    ]);
    expect(t.adapter.bodies.single, {'ClientId': 'client123', 'Token': 'REF'});
  });

  test('Cognito errors become reasons the screens can explain', () async {
    const cases = {
      'CodeMismatchException': AuthFailure.wrongCode,
      'com.amazonaws.cognito#ExpiredCodeException': AuthFailure.expiredCode,
      'UsernameExistsException': AuthFailure.accountExists,
      'UserNotFoundException': AuthFailure.noAccount,
      'NotAuthorizedException': AuthFailure.noAccount,
      'InvalidParameterException': AuthFailure.invalidEmail,
      'LimitExceededException': AuthFailure.tooManyAttempts,
      'TooManyRequestsException': AuthFailure.tooManyAttempts,
      'SomethingNewException': AuthFailure.unknown,
    };
    for (final entry in cases.entries) {
      final t = _make([
        _Reply(400, {'__type': entry.key}),
      ]);
      await expectLater(
        t.api.signUp('kim@example.com'),
        throwsA(
          isA<AuthException>().having((e) => e.failure, entry.key, entry.value),
        ),
      );
    }
    final server = _make([const _Reply(500, {})]);
    await expectLater(
      server.api.signUp('kim@example.com'),
      throwsA(
        isA<AuthException>().having(
          (e) => e.failure,
          '500',
          AuthFailure.network,
        ),
      ),
    );
  });

  test('no connection is reported as a network problem', () async {
    final t = _make([]);
    t.adapter.failWith = DioExceptionType.connectionError;

    await expectLater(
      t.api.startSignIn('kim@example.com'),
      throwsA(
        isA<AuthException>().having(
          (e) => e.failure,
          'failure',
          AuthFailure.network,
        ),
      ),
    );
  });

  test('saved tokens survive a round trip and a damaged copy is ignored', () {
    final tokens = AuthTokens(
      email: 'kim@example.com',
      accessToken: 'A',
      refreshToken: 'R',
      accessExpiresAt: _now,
    );

    final copy = AuthTokens.tryFromJson(
      jsonDecode(jsonEncode(tokens.toJson())),
    );
    expect(copy?.email, 'kim@example.com');
    expect(copy?.accessExpiresAt, _now);
    for (final bad in [
      null,
      'x',
      <String, Object?>{},
      {...tokens.toJson(), 'refreshToken': ''},
      {...tokens.toJson(), 'accessExpiresAt': 'soon'},
    ]) {
      expect(AuthTokens.tryFromJson(bad), isNull);
    }
    expect(
      tokens.needsRefresh(_now.subtract(const Duration(minutes: 5))),
      isFalse,
    );
    expect(
      tokens.needsRefresh(_now.subtract(const Duration(minutes: 1))),
      isTrue,
    );
  });
}
