import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'auth_tokens.dart';

/// Where the phone keeps the tokens between launches.
abstract interface class AuthTokenStore {
  Future<AuthTokens?> read();
  Future<void> write(AuthTokens tokens);
  Future<void> clear();
}

/// The iOS Keychain: encrypted, only readable after the first unlock, and not
/// copied to other devices or iCloud. A failure to read is "not signed in",
/// never a crash.
class SecureAuthTokenStore implements AuthTokenStore {
  SecureAuthTokenStore([FlutterSecureStorage? storage])
    : _storage =
          storage ??
          const FlutterSecureStorage(
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock_this_device,
            ),
          );

  static const _key = 'chordsync.auth.tokens';
  final FlutterSecureStorage _storage;

  @override
  Future<AuthTokens?> read() async {
    try {
      final raw = await _storage.read(key: _key);
      if (raw == null) return null;
      return AuthTokens.tryFromJson(jsonDecode(raw));
    } on Object {
      return null;
    }
  }

  @override
  Future<void> write(AuthTokens tokens) async {
    await _storage.write(key: _key, value: jsonEncode(tokens.toJson()));
  }

  @override
  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Object {
      // Nothing more to do: the controller has already dropped the session.
    }
  }
}

/// Keeps the tokens in memory only. For tests.
class MemoryAuthTokenStore implements AuthTokenStore {
  MemoryAuthTokenStore([this.tokens]);

  AuthTokens? tokens;

  @override
  Future<AuthTokens?> read() async => tokens;

  @override
  Future<void> write(AuthTokens tokens) async => this.tokens = tokens;

  @override
  Future<void> clear() async => tokens = null;
}
