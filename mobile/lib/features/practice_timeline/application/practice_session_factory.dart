import 'dart:io';

import '../../analysis/application/analyzed_practice_session.dart';
import '../../analysis/application/practice_preparation_error.dart';
import 'practice_audio_player.dart';
import 'practice_playback_controller.dart';
import 'practice_playback_synchronizer.dart';

typedef PracticeAudioPlayerFactory = PracticeAudioPlayer Function(File file);

class PracticeSessionFactory {
  PracticeSessionFactory({PracticeAudioPlayerFactory? audioPlayerFactory})
    : _audioPlayerFactory = audioPlayerFactory ?? _createFileAudioPlayer;

  final PracticeAudioPlayerFactory _audioPlayerFactory;

  Future<PreparedPracticeSession> create(
    AnalyzedPracticeSession session, {
    VoidCallback? onPositionChanged,
    VoidCallback? onStatusChanged,
    VoidCallback? onLoopChanged,
  }) async {
    PracticePlaybackSynchronizer? synchronizer;
    try {
      final audioPlayer = _audioPlayerFactory(session.audioFile);
      final playbackController = PracticePlaybackController(session.timeline);
      synchronizer = PracticePlaybackSynchronizer(
        audioPlayer: audioPlayer,
        playbackController: playbackController,
        onPositionChanged: onPositionChanged,
        onStatusChanged: onStatusChanged,
        onLoopChanged: onLoopChanged,
      );
      synchronizer.start();
      await audioPlayer.load();
      return PreparedPracticeSession._(
        analyzedSession: session,
        audioPlayer: audioPlayer,
        playbackController: playbackController,
        synchronizer: synchronizer,
      );
    } on Object {
      await synchronizer?.dispose();
      throw const PracticePreparationException(
        PracticePreparationErrorCode.initializationFailed,
        'The local practice session could not be initialized.',
      );
    }
  }
}

class PreparedPracticeSession {
  PreparedPracticeSession._({
    required this.analyzedSession,
    required this.audioPlayer,
    required this.playbackController,
    required this.synchronizer,
  });

  final AnalyzedPracticeSession analyzedSession;
  final PracticeAudioPlayer audioPlayer;
  final PracticePlaybackController playbackController;
  final PracticePlaybackSynchronizer synchronizer;
  bool _disposed = false;

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await synchronizer.dispose();
  }
}

PracticeAudioPlayer _createFileAudioPlayer(File file) {
  return JustAudioPracticeAudioPlayer(filePath: file.path);
}
