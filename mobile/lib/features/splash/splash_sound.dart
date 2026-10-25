import 'dart:async';

import 'package:just_audio/just_audio.dart';

/// The chord the splash screen strums. It plays at whatever volume the phone
/// is set to; the app never changes the volume itself.
abstract interface class SplashSound {
  /// Gets the sound ready, so [play] starts at once.
  Future<void> load();

  /// Starts the chord. It keeps ringing after the splash is gone.
  Future<void> play();

  Future<void> dispose();
}

/// Plays the recorded C major strum. A sound that fails must never hold up or
/// break the app, so every error here is swallowed.
class JustAudioSplashSound implements SplashSound {
  JustAudioSplashSound();

  static const asset = 'assets/audio/splash_harmonics.wav';

  AudioPlayer? _player;
  bool _ready = false;
  bool _playRequested = false;

  @override
  Future<void> load() async {
    try {
      final player = _player = AudioPlayer();
      await player.setAsset(asset);
      _ready = true;
      // The strum was asked for before the sound finished loading: play now.
      if (_playRequested) unawaited(_start(player));
    } on Object {
      _player = null;
    }
  }

  @override
  Future<void> play() async {
    _playRequested = true;
    final player = _player;
    if (_ready && player != null) await _start(player);
  }

  Future<void> _start(AudioPlayer player) async {
    try {
      await player.play(); // completes when the chord has finished
      await player.dispose();
      _player = null;
    } on Object {
      // No sound is better than a broken launch.
    }
  }

  @override
  Future<void> dispose() async {
    // Once started, the chord is left to ring out and clean up after itself.
    if (_playRequested) return;
    try {
      await _player?.dispose();
    } on Object {
      // Nothing to clean up.
    }
    _player = null;
  }
}

/// Silent: for tests and anywhere a sound is not wanted.
class NoSplashSound implements SplashSound {
  const NoSplashSound();

  @override
  Future<void> load() async {}

  @override
  Future<void> play() async {}

  @override
  Future<void> dispose() async {}
}
