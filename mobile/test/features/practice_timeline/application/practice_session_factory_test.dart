import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/application/practice_preparation_error.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/practice_timeline/application/practice_session_factory.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/fake_practice_audio_player.dart';

void main() {
  test(
    'builds existing playback stack from timeline and original file',
    () async {
      final audio = await _audioFile();
      final timeline = _timeline();
      final analyzed = _session(audio, timeline);
      final player = _RecordingAudioPlayer();
      File? receivedAudio;
      final factory = PracticeSessionFactory(
        audioPlayerFactory: (file) {
          receivedAudio = file;
          return player;
        },
      );

      final practice = await factory.create(analyzed);

      expect(receivedAudio, same(audio));
      expect(practice.analyzedSession, same(analyzed));
      expect(practice.audioPlayer, same(player));
      expect(player.loadCount, 1);
      expect(practice.playbackController.state.chord, 'N');
      expect(practice.playbackController.state.lyricWord, isNull);

      await practice.synchronizer.seek(const Duration(seconds: 2));
      await Future<void>.delayed(Duration.zero);
      expect(practice.playbackController.position, const Duration(seconds: 2));
      expect(practice.playbackController.state.chord, 'C');
      expect(practice.playbackController.state.currentBarNumber, 1);
      expect(practice.playbackController.state.beatNumber, 2);

      await practice.synchronizer.setSpeed(1.5);
      expect(practice.playbackController.position, const Duration(seconds: 2));
      expect(practice.playbackController.state.playbackTime, 2.0);
    },
  );

  test(
    'owns and disposes synchronizer and audio player exactly once',
    () async {
      final player = _RecordingAudioPlayer();
      final practice = await PracticeSessionFactory(
        audioPlayerFactory: (_) => player,
      ).create(_session(await _audioFile(), _timeline()));

      await practice.dispose();
      await practice.dispose();

      expect(player.disposeCount, 1);
      expect(player.hasPositionListener, isFalse);
      expect(player.hasStatusListener, isFalse);
    },
  );

  test(
    'initialization failure cleans partial resources and hides implementation',
    () async {
      final player = _RecordingAudioPlayer(failLoad: true);
      final factory = PracticeSessionFactory(audioPlayerFactory: (_) => player);

      await expectLater(
        factory.create(_session(await _audioFile(), _timeline())),
        throwsA(
          isA<PracticePreparationException>()
              .having(
                (error) => error.code,
                'code',
                PracticePreparationErrorCode.initializationFailed,
              )
              .having(
                (error) => error.toString(),
                'message',
                isNot(contains('just_audio private failure')),
              ),
        ),
      );
      expect(player.disposeCount, 1);
    },
  );

  test('audio adapter creation failure is exposed safely', () async {
    final factory = PracticeSessionFactory(
      audioPlayerFactory: (_) => throw StateError('private plugin failure'),
    );

    await expectLater(
      factory.create(_session(await _audioFile(), _timeline())),
      throwsA(
        isA<PracticePreparationException>()
            .having(
              (error) => error.code,
              'code',
              PracticePreparationErrorCode.initializationFailed,
            )
            .having(
              (error) => error.toString(),
              'message',
              isNot(contains('private plugin failure')),
            ),
      ),
    );
  });
}

class _RecordingAudioPlayer extends FakePracticeAudioPlayer {
  _RecordingAudioPlayer({this.failLoad = false});

  final bool failLoad;
  int loadCount = 0;
  int disposeCount = 0;

  @override
  Future<void> load() async {
    loadCount += 1;
    if (failLoad) throw StateError('just_audio private failure');
    await super.load();
  }

  @override
  Future<void> dispose() async {
    disposeCount += 1;
    await super.dispose();
  }
}

Future<File> _audioFile() async {
  final directory = await Directory.systemTemp.createTemp(
    'chordsync-factory-test-',
  );
  return File('${directory.path}/selected.wav').writeAsBytes([1, 2, 3]);
}

AnalyzedPracticeSession _session(File audio, SharedTimeline timeline) =>
    AnalyzedPracticeSession(
      title: 'Analyzed synthetic',
      job: AnalysisJob(
        jobId: 'job-one',
        status: AnalysisJobStatus.completed,
        createdAt: DateTime.utc(2026),
        updatedAt: DateTime.utc(2026),
        error: null,
        resultAvailable: true,
      ),
      audioFile: audio,
      timeline: timeline,
    );

SharedTimeline _timeline() => const SharedTimeline(
  schemaVersion: 1,
  bpm: 120,
  beatsPerBar: 4,
  beatSource: 'synthetic',
  lyricSource: 'synthetic-empty',
  bars: [
    TimelineBar(
      barNumber: 1,
      startTime: 0,
      endTime: 4,
      beats: [
        TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'N'),
        TimelineEvent(time: 2, beatNumber: 2, isDownbeat: false, chord: 'C'),
      ],
    ),
  ],
  lyrics: [],
);
