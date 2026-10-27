import 'dart:convert';

import 'package:dio/dio.dart';

import 'auth_tokens.dart';
import 'cognito_config.dart';

/// Why a sign-in step did not work, in terms the screens can explain.
enum AuthFailure {
  /// The code is wrong.
  wrongCode,

  /// The code ran out or was used; ask for a new one.
  expiredCode,

  /// Sign-up with an email that already has an account.
  accountExists,

  /// Log in with an email that has no account (or cannot be told apart).
  noAccount,

  /// Too many tries; wait a little.
  tooManyAttempts,

  /// The email address is not acceptable.
  invalidEmail,

  /// The sign-in was refused for good (a revoked or expired session).
  sessionEnded,

  /// The phone could not reach the service.
  network,

  /// Anything else; nothing more is known.
  unknown,
}

class AuthException implements Exception {
  const AuthException(this.failure, [this.detail]);

  final AuthFailure failure;

  /// Cognito's error type, for logs. Never shown, never contains a token.
  final String? detail;

  @override
  String toString() => 'AuthException($failure, $detail)';
}

/// The code Cognito sent, waiting to be typed in. [session] ties the code to
/// this attempt.
class OtpChallenge {
  const OtpChallenge({required this.email, required this.session});

  final String email;
  final String session;
}

/// What the app needs from Cognito. Plain https calls, no SDK.
abstract interface class CognitoApi {
  /// Creates the account (no password) and emails a code.
  Future<OtpChallenge> signUp(String email);

  /// Confirms the account with the emailed code. When Cognito allows it, the
  /// person is signed in at once, with no second code.
  Future<AuthTokens?> confirmSignUp({
    required OtpChallenge challenge,
    required String code,
  });

  /// Emails a sign-in code to an existing account.
  Future<OtpChallenge> startSignIn(String email);

  /// Checks the emailed code and returns the tokens.
  Future<AuthTokens> verifySignIn({
    required OtpChallenge challenge,
    required String code,
  });

  /// Gets a new access token with the refresh token.
  Future<AuthTokens> refresh(AuthTokens tokens);

  /// Ends the session on the server. Best effort.
  Future<void> revoke(AuthTokens tokens);
}

class DioCognitoApi implements CognitoApi {
  DioCognitoApi({
    required CognitoConfig config,
    Dio? dio,
    DateTime Function()? clock,
  }) : _config = config,
       _clock = clock ?? DateTime.now,
       _dio =
           dio ??
           Dio(
             BaseOptions(
               baseUrl: config.endpoint,
               connectTimeout: const Duration(seconds: 15),
               receiveTimeout: const Duration(seconds: 20),
               // Cognito answers errors with a 400 and a JSON body we read.
               validateStatus: (_) => true,
             ),
           );

  final CognitoConfig _config;
  final Dio _dio;
  final DateTime Function() _clock;

  @override
  Future<OtpChallenge> signUp(String email) async {
    final response = await _call('SignUp', {
      'ClientId': _config.clientId,
      'Username': email,
      'UserAttributes': [
        {'Name': 'email', 'Value': email},
      ],
    });
    return OtpChallenge(
      email: email,
      session: _text(response['Session']) ?? '',
    );
  }

  @override
  Future<AuthTokens?> confirmSignUp({
    required OtpChallenge challenge,
    required String code,
  }) async {
    final response = await _call('ConfirmSignUp', {
      'ClientId': _config.clientId,
      'Username': challenge.email,
      'ConfirmationCode': code,
      if (challenge.session.isNotEmpty) 'Session': challenge.session,
    });
    final session = _text(response['Session']);
    if (session == null) return null;
    try {
      // Sign in straight away with the session the confirmation returned.
      final signedIn = await _call('InitiateAuth', {
        'ClientId': _config.clientId,
        'AuthFlow': 'USER_AUTH',
        'AuthParameters': {'USERNAME': challenge.email},
        'Session': session,
      });
      return _tokensOrNull(challenge.email, signedIn);
    } on AuthException {
      return null; // the screens fall back to a normal sign-in
    }
  }

  @override
  Future<OtpChallenge> startSignIn(String email) async {
    var response = await _call('InitiateAuth', {
      'ClientId': _config.clientId,
      'AuthFlow': 'USER_AUTH',
      'AuthParameters': {'USERNAME': email, 'PREFERRED_CHALLENGE': 'EMAIL_OTP'},
    });
    if (response['ChallengeName'] == 'SELECT_CHALLENGE') {
      response = await _call('RespondToAuthChallenge', {
        'ClientId': _config.clientId,
        'ChallengeName': 'SELECT_CHALLENGE',
        'Session': _text(response['Session']),
        'ChallengeResponses': {'USERNAME': email, 'ANSWER': 'EMAIL_OTP'},
      });
    }
    final session = _text(response['Session']);
    if (response['ChallengeName'] != 'EMAIL_OTP' || session == null) {
      throw const AuthException(AuthFailure.unknown, 'unexpected challenge');
    }
    return OtpChallenge(email: email, session: session);
  }

  @override
  Future<AuthTokens> verifySignIn({
    required OtpChallenge challenge,
    required String code,
  }) async {
    final response = await _call('RespondToAuthChallenge', {
      'ClientId': _config.clientId,
      'ChallengeName': 'EMAIL_OTP',
      'Session': challenge.session,
      'ChallengeResponses': {
        'USERNAME': challenge.email,
        'EMAIL_OTP_CODE': code,
      },
    });
    final tokens = _tokensOrNull(challenge.email, response);
    if (tokens == null) {
      // A wrong code makes Cognito hand back the same challenge with a new session.
      throw const AuthException(AuthFailure.wrongCode, 'challenge repeated');
    }
    return tokens;
  }

  @override
  Future<AuthTokens> refresh(AuthTokens tokens) async {
    final response = await _call('InitiateAuth', {
      'ClientId': _config.clientId,
      'AuthFlow': 'REFRESH_TOKEN_AUTH',
      'AuthParameters': {'REFRESH_TOKEN': tokens.refreshToken},
    });
    final result = _map(response['AuthenticationResult']);
    final access = _text(result?['AccessToken']);
    if (access == null) {
      throw const AuthException(AuthFailure.sessionEnded, 'no access token');
    }
    return tokens.withAccess(access, _expiry(result));
  }

  @override
  Future<void> revoke(AuthTokens tokens) async {
    try {
      await _call('RevokeToken', {
        'ClientId': _config.clientId,
        'Token': tokens.refreshToken,
      });
    } on AuthException {
      // Signing out on this phone must work even if the server cannot be reached.
    }
  }

  AuthTokens? _tokensOrNull(String email, Map<String, Object?> response) {
    final result = _map(response['AuthenticationResult']);
    final access = _text(result?['AccessToken']);
    final refresh = _text(result?['RefreshToken']);
    if (access == null || refresh == null) return null;
    return AuthTokens(
      email: email,
      accessToken: access,
      refreshToken: refresh,
      accessExpiresAt: _expiry(result),
    );
  }

  DateTime _expiry(Map<String, Object?>? result) {
    final seconds = result?['ExpiresIn'];
    final lifetime = seconds is num ? seconds.toInt() : 3600;
    return _clock().add(Duration(seconds: lifetime));
  }

  Future<Map<String, Object?>> _call(
    String action,
    Map<String, Object?> body,
  ) async {
    final Response<Object?> response;
    try {
      response = await _dio.post<Object?>(
        '',
        // Sent as ready-made JSON text: Dio only encodes bodies for the plain
        // "application/json" type, and Cognito rejects anything else.
        data: jsonEncode(body),
        options: Options(
          // Cognito's content type is not "application/json", so Dio would leave
          // the body as text; it is decoded below.
          responseType: ResponseType.plain,
          contentType: 'application/x-amz-json-1.1',
          headers: {
            'X-Amz-Target': 'AWSCognitoIdentityProviderService.$action',
          },
        ),
      );
    } on DioException catch (error) {
      throw AuthException(AuthFailure.network, error.type.name);
    }
    final data = _decode(response.data);
    final status = response.statusCode ?? 0;
    if (status >= 200 && status < 300) return data;
    // The error type looks like "CodeMismatchException" or "...#CodeMismatchException".
    final type = '${data['__type'] ?? data['code'] ?? ''}'.split('#').last;
    throw AuthException(
      _failureFor(type, status),
      type.isEmpty ? '$status' : type,
    );
  }

  static AuthFailure _failureFor(String type, int status) => switch (type) {
    'CodeMismatchException' => AuthFailure.wrongCode,
    'ExpiredCodeException' => AuthFailure.expiredCode,
    'UsernameExistsException' => AuthFailure.accountExists,
    'UserNotFoundException' => AuthFailure.noAccount,
    'InvalidParameterException' => AuthFailure.invalidEmail,
    'LimitExceededException' ||
    'TooManyRequestsException' ||
    'TooManyFailedAttemptsException' => AuthFailure.tooManyAttempts,
    'NotAuthorizedException' ||
    'UserNotConfirmedException' => AuthFailure.noAccount,
    _ => status >= 500 ? AuthFailure.network : AuthFailure.unknown,
  };

  static Map<String, Object?> _decode(Object? body) {
    if (body is! String || body.isEmpty) return _map(body) ?? const {};
    try {
      return _map(jsonDecode(body)) ?? const {};
    } on FormatException {
      return const {};
    }
  }

  static Map<String, Object?>? _map(Object? value) =>
      value is Map ? Map<String, Object?>.from(value) : null;

  static String? _text(Object? value) =>
      value is String && value.isNotEmpty ? value : null;
}
