import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'user_profile.dart';

/// Keeps the profile from sign-up on this phone until it can be sent to the
/// account.
abstract interface class ProfileStore {
  Future<UserProfile?> read();
  Future<void> write(UserProfile profile);
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

  static const _key = 'chordsync.profile';
  final FlutterSecureStorage _storage;

  @override
  Future<UserProfile?> read() async {
    try {
      final raw = await _storage.read(key: _key);
      return raw == null ? null : UserProfile.tryFromJson(jsonDecode(raw));
    } on Object {
      return null;
    }
  }

  @override
  Future<void> write(UserProfile profile) async {
    await _storage.write(key: _key, value: jsonEncode(profile.toJson()));
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
  UserProfile? profile;

  @override
  Future<UserProfile?> read() async => profile;

  @override
  Future<void> write(UserProfile profile) async => this.profile = profile;

  @override
  Future<void> clear() async => profile = null;
}
