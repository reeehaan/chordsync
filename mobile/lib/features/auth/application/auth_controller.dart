import 'dart:async';

import 'package:flutter/foundation.dart';

import '../data/auth_token_store.dart';
import '../data/auth_tokens.dart';
import '../data/cognito_api.dart';

enum AuthStatus {
  /// Still reading the phone's storage.
  loading,
  signedOut,
  signedIn,
}

/// Signs people in with an emailed code, keeps them signed in, and hands the
/// API a fresh access token. No passwords.
///
/// Create account: [beginSignUp] sends a code, [submitCode] confirms it and
/// signs the person in. Log in: [beginLogIn] sends a code, [submitCode] checks
/// it. [accessToken] renews the session quietly when it is about to run out.
class AuthController extends ChangeNotifier {
  AuthController({
    required this._api,
    required this._store,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  final CognitoApi _api;
  final AuthTokenStore _store;
  final DateTime Function() _clock;

  AuthStatus _status = AuthStatus.loading;
  AuthTokens? _tokens;
  OtpChallenge? _challenge;
  bool _signingUp = false;
  bool _busy = false;
  AuthFailure? _failure;
  Future<AuthTokens?>? _refreshing;

  AuthStatus get status => _status;
  bool get isSignedIn => _status == AuthStatus.signedIn;

  /// The signed-in person's email, if any.
  String? get email => _tokens?.email;

  /// The email a code was sent to, while one is waiting to be typed in.
  String? get pendingEmail => _challenge?.email;

  /// True between asking for a code and typing it in.
  bool get waitingForCode => _challenge != null;

  /// True while a request is in flight; screens disable their buttons.
  bool get busy => _busy;

  /// What went wrong with the last step, until the next one starts.
  AuthFailure? get failure => _failure;

  /// Reads the saved session. Call once at start-up.
  Future<void> restore() async {
    _tokens = await _store.read();
    _status = _tokens == null ? AuthStatus.signedOut : AuthStatus.signedIn;
    notifyListeners();
  }

  /// Creates an account and emails the code. Returns true when the code is on
  /// its way.
  Future<bool> beginSignUp(String email) =>
      _begin(email, signUp: true, send: _api.signUp);

  /// Emails a sign-in code to an existing account.
  Future<bool> beginLogIn(String email) =>
      _begin(email, signUp: false, send: _api.startSignIn);

  /// Sends the same kind of code again.
  Future<bool> resendCode() {
    final email = _challenge?.email;
    if (email == null) return Future.value(false);
    return _signingUp ? beginSignUp(email) : beginLogIn(email);
  }

  /// Checks the typed code. True when the person is now signed in.
  Future<bool> submitCode(String code) async {
    final challenge = _challenge;
    final trimmed = code.trim();
    if (challenge == null || _busy) return false;
    if (!RegExp(r'^\d{6}$').hasMatch(trimmed)) {
      _failure = AuthFailure.wrongCode;
      notifyListeners();
      return false;
    }
    return _run(() async {
      final AuthTokens? tokens;
      if (_signingUp) {
        tokens = await _api.confirmSignUp(challenge: challenge, code: trimmed);
        if (tokens == null) {
          // The account is confirmed but Cognito did not sign us in: ask for a
          // normal sign-in code instead of making the person start again.
          _challenge = await _api.startSignIn(challenge.email);
          _signingUp = false;
          return false;
        }
      } else {
        tokens = await _api.verifySignIn(challenge: challenge, code: trimmed);
      }
      await _signedIn(tokens);
      return true;
    });
  }

  /// Gives up on the code that is waiting (the person went back).
  void cancel() {
    _challenge = null;
    _failure = null;
    notifyListeners();
  }

  /// Ends the session here and on the server. Works without a connection.
  Future<void> signOut() async {
    final tokens = _tokens;
    _tokens = null;
    _challenge = null;
    _failure = null;
    _status = AuthStatus.signedOut;
    notifyListeners();
    await _store.clear();
    if (tokens != null) await _api.revoke(tokens);
  }

  /// A valid access token for the API, renewed first if it is nearly out of
  /// time. Null when nobody is signed in or the session has ended.
  Future<String?> accessToken() async {
    final tokens = _tokens;
    if (tokens == null) return null;
    if (!tokens.needsRefresh(_clock())) return tokens.accessToken;
    final renewed = await (_refreshing ??= _refresh(
      tokens,
    ).whenComplete(() => _refreshing = null));
    return renewed?.accessToken;
  }

  Future<AuthTokens?> _refresh(AuthTokens tokens) async {
    try {
      final renewed = await _api.refresh(tokens);
      _tokens = renewed;
      await _store.write(renewed);
      return renewed;
    } on AuthException catch (error) {
      if (error.failure == AuthFailure.network ||
          error.failure == AuthFailure.tooManyAttempts) {
        // A bad connection is not a reason to sign anyone out. Use the old
        // token if it still has time left.
        return tokens.accessExpiresAt.isAfter(_clock()) ? tokens : null;
      }
      await _endSession();
      return null;
    }
  }

  Future<void> _endSession() async {
    _tokens = null;
    _status = AuthStatus.signedOut;
    await _store.clear();
    notifyListeners();
  }

  Future<bool> _begin(
    String email, {
    required bool signUp,
    required Future<OtpChallenge> Function(String) send,
  }) async {
    if (_busy) return false;
    final normal = normalizeEmail(email);
    if (normal == null) {
      _failure = AuthFailure.invalidEmail;
      notifyListeners();
      return false;
    }
    return _run(() async {
      _challenge = await send(normal);
      _signingUp = signUp;
      return true;
    });
  }

  Future<void> _signedIn(AuthTokens tokens) async {
    _tokens = tokens;
    _challenge = null;
    await _store.write(tokens);
    _status = AuthStatus.signedIn;
  }

  Future<bool> _run(Future<bool> Function() step) async {
    _busy = true;
    _failure = null;
    notifyListeners();
    try {
      return await step();
    } on AuthException catch (error) {
      _failure = error.failure;
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  /// A tidy lower-case address, or null when it cannot be one.
  static String? normalizeEmail(String raw) {
    final email = raw.trim().toLowerCase();
    if (email.length > 254) return null;
    return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email) ? email : null;
  }
}
