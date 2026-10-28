import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// How the app picks light or dark: follow the phone, or stay on one.
enum Appearance {
  system('Auto'),
  light('Light'),
  dark('Dark');

  const Appearance(this.label);

  final String label;

  /// Whether the dark palette is in use, given what the phone is set to.
  bool resolvesDark(Brightness phone) => switch (this) {
    Appearance.system => phone == Brightness.dark,
    Appearance.light => false,
    Appearance.dark => true,
  };
}

/// Where the choice is kept between launches.
abstract interface class AppearanceStore {
  Future<Appearance?> read();
  Future<void> write(Appearance appearance);
}

class MemoryAppearanceStore implements AppearanceStore {
  Appearance? value;

  @override
  Future<Appearance?> read() async => value;

  @override
  Future<void> write(Appearance appearance) async => value = appearance;
}

/// A convenience, so a failure to read or write is never an error.
class SecureAppearanceStore implements AppearanceStore {
  SecureAppearanceStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'chordsync.appearance';
  final FlutterSecureStorage _storage;

  @override
  Future<Appearance?> read() async {
    try {
      final name = await _storage.read(key: _key);
      return Appearance.values.where((a) => a.name == name).firstOrNull;
    } on Object {
      return null;
    }
  }

  @override
  Future<void> write(Appearance appearance) async {
    try {
      await _storage.write(key: _key, value: appearance.name);
    } on Object {
      // The choice still applies until the app closes.
    }
  }
}

class AppearanceController extends ChangeNotifier {
  AppearanceController({required this._store});

  final AppearanceStore _store;
  Appearance _appearance = Appearance.system;

  Appearance get appearance => _appearance;

  Future<void> load() async {
    final saved = await _store.read();
    if (saved != null && saved != _appearance) {
      _appearance = saved;
      notifyListeners();
    }
  }

  Future<void> select(Appearance next) async {
    if (next == _appearance) return;
    _appearance = next;
    notifyListeners();
    await _store.write(next);
  }
}
