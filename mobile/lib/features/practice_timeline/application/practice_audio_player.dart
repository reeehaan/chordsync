import 'dart:async';

import 'package:just_audio/just_audio.dart';

import 'practice_playback_status.dart';
import 'practice_playback_speeds.dart';

abstract interface class PracticeAudioPlayer {
  Stream<Duration> get positionStream;
  Stream<PracticePlaybackStatus> get statusStream;
  Duration get position;
  Duration? get duration;
  PracticePlaybackStatus get status;
  double get speed;

  Future<void> load();
  Future<void> play();
  Future<void> pause();
  Future<void> seek(Duration position);
  Future<void> setSpeed(double speed);
  Future<void> dispose();
}

class JustAudioPracticeAudioPlayer implements PracticeAudioPlayer {
  JustAudioPracticeAudioPlayer({
    this.assetPath = 'assets/practice_audio/synthetic_practice.wav',
    this.filePath,
  }) {
    _playerStateSubscription = _player.playerStateStream.listen(
      _handlePlayerState,
      onError: (_) => _setStatus(PracticePlaybackStatus.error),
    );
  }

  final String assetPath;
  final String? filePath;
  final AudioPlayer _player = AudioPlayer();
  final _statuses = StreamController<PracticePlaybackStatus>.broadcast();
  late final StreamSubscription<PlayerState> _playerStateSubscription;
  PracticePlaybackStatus _status = PracticePlaybackStatus.loading;

  @override
  Stream<Duration> get positionStream => _player.positionStream;

  @override
  Stream<PracticePlaybackStatus> get statusStream => _statuses.stream;

  @override
  Duration get position => _player.position;

  @override
  Duration? get duration => _player.duration;

  @override
  PracticePlaybackStatus get status => _status;

  @override
  double get speed => _player.speed;

  @override
  Future<void> load() async {
    try {
      final localFilePath = filePath;
      await _player.setAudioSource(
        localFilePath == null
            ? AudioSource.asset(assetPath)
            : AudioSource.file(localFilePath),
      );
      _setStatus(PracticePlaybackStatus.paused);
    } on Object {
      _setStatus(PracticePlaybackStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> play() async {
    try {
      await _player.play();
    } on Object {
      _setStatus(PracticePlaybackStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> pause() async {
    try {
      await _player.pause();
    } on Object {
      _setStatus(PracticePlaybackStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> seek(Duration position) async {
    try {
      await _player.seek(position);
      final audioDuration = duration;
      if (audioDuration != null && position >= audioDuration) {
        _setStatus(PracticePlaybackStatus.completed);
      } else if (_status == PracticePlaybackStatus.completed) {
        _setStatus(PracticePlaybackStatus.paused);
      }
    } on Object {
      _setStatus(PracticePlaybackStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> setSpeed(double speed) async {
    if (!PracticePlaybackSpeeds.isSupported(speed)) {
      throw ArgumentError.value(speed, 'speed', 'Unsupported practice speed');
    }
    try {
      await _player.setSpeed(speed);
    } on Object {
      _setStatus(PracticePlaybackStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> dispose() async {
    await _playerStateSubscription.cancel();
    await _player.dispose();
    await _statuses.close();
  }

  void _handlePlayerState(PlayerState state) {
    if (state.processingState == ProcessingState.completed) {
      _setStatus(PracticePlaybackStatus.completed);
    } else if (state.playing) {
      _setStatus(PracticePlaybackStatus.playing);
    } else if (state.processingState == ProcessingState.ready) {
      _setStatus(PracticePlaybackStatus.paused);
    }
  }

  void _setStatus(PracticePlaybackStatus status) {
    if (_status == status) return;
    _status = status;
    _statuses.add(status);
  }
}
