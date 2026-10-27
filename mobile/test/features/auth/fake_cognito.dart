import 'package:chordsync/features/auth/data/auth_tokens.dart';
import 'package:chordsync/features/auth/data/cognito_api.dart';

/// A stand-in for Cognito that records what it was asked and can be made to fail.
class FakeCognito implements CognitoApi {
  final calls = <String>[];
  AuthFailure? failNext;
  bool autoSignIn = true;
  int refreshCount = 0;
  AuthFailure? refreshFailure;

  AuthTokens tokens(String email, {String access = 'access-1'}) => AuthTokens(
    email: email,
    accessToken: access,
    refreshToken: 'refresh-1',
    accessExpiresAt: DateTime.utc(2026, 1, 1, 1),
  );

  void _maybeFail() {
    final failure = failNext;
    if (failure != null) {
      failNext = null;
      throw AuthException(failure, 'test');
    }
  }

  @override
  Future<OtpChallenge> signUp(String email) async {
    calls.add('signUp:$email');
    _maybeFail();
    return OtpChallenge(email: email, session: 'signup-session');
  }

  @override
  Future<AuthTokens?> confirmSignUp({
    required OtpChallenge challenge,
    required String code,
  }) async {
    calls.add('confirm:$code');
    _maybeFail();
    return autoSignIn ? tokens(challenge.email) : null;
  }

  @override
  Future<OtpChallenge> startSignIn(String email) async {
    calls.add('startSignIn:$email');
    _maybeFail();
    return OtpChallenge(email: email, session: 'signin-session');
  }

  @override
  Future<AuthTokens> verifySignIn({
    required OtpChallenge challenge,
    required String code,
  }) async {
    calls.add('verify:$code');
    _maybeFail();
    return tokens(challenge.email);
  }

  @override
  Future<AuthTokens> refresh(AuthTokens current) async {
    calls.add('refresh');
    refreshCount++;
    final failure = refreshFailure;
    if (failure != null) throw AuthException(failure);
    await Future<void>.delayed(Duration.zero);
    return current.withAccess('access-2', DateTime.utc(2026, 1, 1, 2));
  }

  @override
  Future<void> revoke(AuthTokens current) async => calls.add('revoke');
}
