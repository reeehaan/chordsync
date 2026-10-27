import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'user_profile.dart';

/// A profile kept on this phone, with the email it belongs to. The email stops
/// one person's unfinished sign-up from ending up on someone else's account.
class LocalProfile {
  const LocalProfile({required this.email, required this.profile});

  final String email;
  final UserProfile profile;

  Map<String, Object?> toJson() => {
    'email': email,
    'profile': profile.toJson(),
  };

  static LocalProfile? tryFromJson(Object? value) {
    if (value is! Map) return null;
    final email = value['email'];
    final profile = UserProfile.tryFromJson(value['profile']);
    if (email is! String || email.isEmpty || profile == null) return null;
    return LocalProfile(email: email, profile: profile);
  }
}

/// Keeps the profile from sign-up on this phone until it has been sent to the
/// account, and a copy of it afterwards so the app can show it offline.
abstract interface class ProfileStore {
  Future<LocalProfile?> read();
  Future<void> write(UserProfile profile, {required String email});
  Future<void> clear();
}

class SecureProfileStore implements ProfileStore {
  SecureProfileStore([FlutterSecureStorage? storage])
    : _storage =
          storage ??
          const FlutterSecureStorage(
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock_this_device,
            ),
          );

  static const _key = 'chordsync.profile.v2';
  final FlutterSecureStorage _storage;

  @override
  Future<LocalProfile?> read() async {
    try {
      final raw = await _storage.read(key: _key);
      return raw == null ? null : LocalProfile.tryFromJson(jsonDecode(raw));
    } on Object {
      return null;
    }
  }

  @override
  Future<void> write(UserProfile profile, {required String email}) async {
    final local = LocalProfile(email: email, profile: profile);
    await _storage.write(key: _key, value: jsonEncode(local.toJson()));
  }

  @override
  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Object {
      // Nothing to do.
    }
  }
}

class MemoryProfileStore implements ProfileStore {
  LocalProfile? local;

  /// The saved profile, for tests.
  UserProfile? get profile => local?.profile;

  @override
  Future<LocalProfile?> read() async => local;

  @override
  Future<void> write(UserProfile profile, {required String email}) async =>
      local = LocalProfile(email: email, profile: profile);

  @override
  Future<void> clear() async => local = null;
}
