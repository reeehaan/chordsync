import 'dart:async';

import 'practice_audio_player.dart';
import 'practice_loop.dart';
import 'practice_playback_controller.dart';
import 'practice_playback_status.dart';
import 'practice_playback_speeds.dart';

class PracticePlaybackSynchronizer {
  PracticePlaybackSynchronizer({
    required this.audioPlayer,
    required this.playbackController,
    this.onPositionChanged,
    this.onStatusChanged,
    this.onLoopChanged,
  });

  final PracticeAudioPlayer audioPlayer;
  final PracticePlaybackController playbackController;
  final VoidCallback? onPositionChanged;
  final VoidCallback? onStatusChanged;
  final VoidCallback? onLoopChanged;

  StreamSubscription<Duration>? _positionSubscription;
  StreamSubscription<PracticePlaybackStatus>? _statusSubscription;
  PracticeLoop? _loop;
  Duration? _pendingLoopStart;
  bool _ignoreNextPositionForLoop = false;
  bool _suppressNextCompletionLoop = false;
  bool _ignoreCompletionAfterLoop = false;
  bool _loopBoundaryArmed = true;
  bool _loopSeekInProgress = false;
  bool _playbackIntent = false;

  PracticePlaybackStatus get status => audioPlayer.status;
  Duration? get duration => audioPlayer.duration;
  PracticeLoop? get loop => _loop;
  Duration? get loopStart => _loop?.start ?? _pendingLoopStart;
  Duration? get loopEnd => _loop?.end;
  double get speed => audioPlayer.speed;
  bool get canSeekToPreviousBar =>
      playbackController.previousBarStart(audioPlayer.position) != null;
  bool get canSeekToNextBar =>
      playbackController.nextBarStart(audioPlayer.position) != null;

  void start() {
    _positionSubscription ??= audioPlayer.positionStream.listen(
      (position) => unawaited(_handlePosition(position)),
    );
    _statusSubscription ??= audioPlayer.statusStream.listen(
      (status) => unawaited(_handleStatus(status)),
    );
  }

  Future<void> play() async {
    if (status == PracticePlaybackStatus.completed) {
      await audioPlayer.seek(Duration.zero);
    }
    await audioPlayer.play();
    _playbackIntent = true;
  }

  Future<void> pause() async {
    await audioPlayer.pause();
    _playbackIntent = false;
  }

  Future<bool> setSpeed(double speed) async {
    if (!PracticePlaybackSpeeds.isSupported(speed)) return false;
    await audioPlayer.setSpeed(speed);
    return true;
  }

  Future<void> seek(Duration position) async {
    _ignoreNextPositionForLoop = true;
    final activeLoop = _loop;
    _suppressNextCompletionLoop =
        activeLoop?.enabled == true && position >= activeLoop!.end;
    await audioPlayer.seek(position);
  }

  Future<bool> seekToPreviousBar() async {
    final target = playbackController.previousBarStart(audioPlayer.position);
    if (target == null) return false;
    await seek(target);
    return true;
  }

  Future<bool> seekToNextBar() async {
    final target = playbackController.nextBarStart(audioPlayer.position);
    if (target == null) return false;
    await seek(target);
    return true;
  }

  bool setLoopStart(Duration position) {
    final audioDuration = duration;
    if (position.isNegative ||
        audioDuration == null ||
        position >= audioDuration) {
      return false;
    }

    final currentLoop = _loop;
    if (currentLoop != null) {
      if (position >= currentLoop.end) return false;
      _loop = currentLoop.copyWith(start: position);
    } else {
      _pendingLoopStart = position;
    }
    _loopBoundaryArmed = true;
    onLoopChanged?.call();
    return true;
  }

  bool setLoopEnd(Duration position) {
    final start = loopStart;
    final audioDuration = duration;
    if (start == null ||
        audioDuration == null ||
        position <= start ||
        position > audioDuration) {
      return false;
    }

    _loop = PracticeLoop(
      start: start,
      end: position,
      enabled: _loop?.enabled ?? false,
    );
    _pendingLoopStart = null;
    _loopBoundaryArmed = true;
    onLoopChanged?.call();
    return true;
  }

  bool enableLoop() {
    final currentLoop = _loop;
    if (currentLoop == null) return false;
    if (!currentLoop.enabled) {
      _loop = currentLoop.copyWith(enabled: true);
      _loopBoundaryArmed = true;
      onLoopChanged?.call();
    }
    return true;
  }

  void disableLoop() {
    final currentLoop = _loop;
    if (currentLoop == null || !currentLoop.enabled) return;
    _loop = currentLoop.copyWith(enabled: false);
    _loopBoundaryArmed = true;
    onLoopChanged?.call();
  }

  void clearLoop() {
    if (_loop == null && _pendingLoopStart == null) return;
    _loop = null;
    _pendingLoopStart = null;
    _loopBoundaryArmed = true;
    onLoopChanged?.call();
  }

  Future<void> dispose() async {
    await _positionSubscription?.cancel();
    _positionSubscription = null;
    await _statusSubscription?.cancel();
    _statusSubscription = null;
    await audioPlayer.dispose();
  }

  Future<void> _handlePosition(Duration position) async {
    playbackController.setPosition(position);
    onPositionChanged?.call();

    if (_ignoreNextPositionForLoop) {
      _ignoreNextPositionForLoop = false;
      return;
    }

    final activeLoop = _loop;
    if (activeLoop == null || !activeLoop.enabled) return;
    if (position <= activeLoop.start) _loopBoundaryArmed = true;
    if (position >= activeLoop.end && _loopBoundaryArmed) {
      await _returnToLoopStart(activeLoop, resumePlayback: _playbackIntent);
    }
  }

  Future<void> _handleStatus(PracticePlaybackStatus status) async {
    if (status == PracticePlaybackStatus.completed) {
      final activeLoop = _loop;
      if (_ignoreCompletionAfterLoop) {
        _ignoreCompletionAfterLoop = false;
      } else if (_suppressNextCompletionLoop) {
        _suppressNextCompletionLoop = false;
        _playbackIntent = false;
      } else if (activeLoop != null &&
          activeLoop.enabled &&
          audioPlayer.position >= activeLoop.end &&
          _loopBoundaryArmed) {
        await _returnToLoopStart(activeLoop, resumePlayback: true);
      } else if (!_loopSeekInProgress) {
        _playbackIntent = false;
        final audioDuration = audioPlayer.duration;
        if (audioDuration != null) {
          playbackController.setPosition(audioDuration);
          onPositionChanged?.call();
        }
      }
    }
    onStatusChanged?.call();
  }

  Future<void> _returnToLoopStart(
    PracticeLoop activeLoop, {
    required bool resumePlayback,
  }) async {
    if (_loopSeekInProgress) return;
    _loopSeekInProgress = true;
    _loopBoundaryArmed = false;
    final audioDuration = duration;
    if (audioDuration != null && activeLoop.end >= audioDuration) {
      _ignoreCompletionAfterLoop = true;
    }
    try {
      await audioPlayer.seek(activeLoop.start);
      if (resumePlayback) await audioPlayer.play();
    } finally {
      _loopSeekInProgress = false;
    }
  }
}

typedef VoidCallback = void Function();
