import 'dart:async';

import 'package:chordsync/features/practice_timeline/application/practice_audio_player.dart';
import 'package:chordsync/features/practice_timeline/application/practice_playback_status.dart';
import 'package:chordsync/features/practice_timeline/application/practice_playback_speeds.dart';

class FakePracticeAudioPlayer implements PracticeAudioPlayer {
  final _positions = StreamController<Duration>.broadcast();
  final _statuses = StreamController<PracticePlaybackStatus>.broadcast();

  @override
  Stream<Duration> get positionStream => _positions.stream;

  @override
  Stream<PracticePlaybackStatus> get statusStream => _statuses.stream;

  @override
  Duration get position => _position;
  Duration _position = Duration.zero;

  @override
  Duration? get duration => const Duration(seconds: 9);

  @override
  PracticePlaybackStatus get status => _status;
  PracticePlaybackStatus _status = PracticePlaybackStatus.loading;

  @override
  double get speed => _speed;
  double _speed = PracticePlaybackSpeeds.defaultSpeed;

  bool get isPlaying => status == PracticePlaybackStatus.playing;
  bool disposed = false;
  bool get hasPositionListener => _positions.hasListener;
  bool get hasStatusListener => _statuses.hasListener;
  final seekCalls = <Duration>[];
  final speedCalls = <double>[];

  void emit(Duration position) {
    _position = position;
    _positions.add(position);
  }

  void emitStatus(PracticePlaybackStatus status) {
    _status = status;
    _statuses.add(status);
  }

  void complete() {
    emit(duration!);
    emitStatus(PracticePlaybackStatus.completed);
  }

  @override
  Future<void> load() async {
    emitStatus(PracticePlaybackStatus.paused);
  }

  @override
  Future<void> play() async {
    emitStatus(PracticePlaybackStatus.playing);
  }

  @override
  Future<void> pause() async {
    emitStatus(PracticePlaybackStatus.paused);
  }

  @override
  Future<void> seek(Duration position) async {
    seekCalls.add(position);
    emit(position);
    if (position >= duration!) {
      emitStatus(PracticePlaybackStatus.completed);
    } else if (status == PracticePlaybackStatus.completed) {
      emitStatus(PracticePlaybackStatus.paused);
    }
  }

  @override
  Future<void> setSpeed(double speed) async {
    if (!PracticePlaybackSpeeds.isSupported(speed)) {
      throw ArgumentError.value(speed, 'speed', 'Unsupported practice speed');
    }
    speedCalls.add(speed);
    _speed = speed;
  }

  @override
  Future<void> dispose() async {
    disposed = true;
    await _positions.close();
    await _statuses.close();
  }
}
