import 'package:chordsync/features/practice_timeline/application/practice_playback_controller.dart';
import 'package:chordsync/features/practice_timeline/application/practice_playback_status.dart';
import 'package:chordsync/features/practice_timeline/application/practice_playback_synchronizer.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/fake_practice_audio_player.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late PracticePlaybackController controller;
  late FakePracticeAudioPlayer player;
  late PracticePlaybackSynchronizer synchronizer;

  setUp(() async {
    final timeline = await SharedTimelineAssetLoader.load();
    controller = PracticePlaybackController(timeline);
    player = FakePracticeAudioPlayer();
    synchronizer = PracticePlaybackSynchronizer(
      audioPlayer: player,
      playbackController: controller,
    );
    synchronizer.start();
    await player.load();
    await pumpEventQueue();
  });

  tearDown(() async {
    if (!player.disposed) await synchronizer.dispose();
  });

  void configureLoop() {
    expect(synchronizer.setLoopStart(const Duration(seconds: 2)), isTrue);
    expect(synchronizer.setLoopEnd(const Duration(seconds: 6)), isTrue);
    expect(synchronizer.enableLoop(), isTrue);
  }

  test('defaults to 1.0x and rejects unsupported speed', () async {
    expect(synchronizer.speed, 1.0);
    expect(await synchronizer.setSpeed(0.6), isFalse);
    expect(player.speedCalls, isEmpty);
    await expectLater(player.setSpeed(0.6), throwsArgumentError);
    expect(synchronizer.speed, 1.0);
  });

  test(
    'paused speed changes preserve position and persist on resume',
    () async {
      await synchronizer.seek(const Duration(seconds: 4));
      await pumpEventQueue();

      expect(await synchronizer.setSpeed(0.5), isTrue);
      expect(synchronizer.speed, 0.5);
      expect(controller.position, const Duration(seconds: 4));
      expect(synchronizer.status, PracticePlaybackStatus.paused);

      await synchronizer.play();
      await pumpEventQueue();
      expect(synchronizer.speed, 0.5);
      expect(synchronizer.status, PracticePlaybackStatus.playing);
      expect(controller.position, const Duration(seconds: 4));
    },
  );

  test('playing speed change does not pause or reset media position', () async {
    await synchronizer.seek(const Duration(seconds: 4));
    await synchronizer.play();
    await pumpEventQueue();

    expect(await synchronizer.setSpeed(1.5), isTrue);
    expect(synchronizer.speed, 1.5);
    expect(synchronizer.status, PracticePlaybackStatus.playing);
    expect(controller.position, const Duration(seconds: 4));
  });

  test('musical state at fixed media time is independent of speed', () async {
    await synchronizer.seek(const Duration(seconds: 4));
    await pumpEventQueue();
    final original = controller.state;

    await synchronizer.setSpeed(0.5);
    final slowed = controller.state;
    await synchronizer.setSpeed(1.5);
    final accelerated = controller.state;

    for (final state in [slowed, accelerated]) {
      expect(state.playbackTime, original.playbackTime);
      expect(state.currentChord, original.currentChord);
      expect(state.currentBarNumber, original.currentBarNumber);
      expect(state.beatNumber, original.beatNumber);
      expect(state.activeLyricWord, original.activeLyricWord);
      expect(state.chordProgression, original.chordProgression);
    }
  });

  test('speed changes preserve A/B media-time markers', () async {
    configureLoop();

    await synchronizer.setSpeed(1.5);

    expect(synchronizer.loop?.start, const Duration(seconds: 2));
    expect(synchronizer.loop?.end, const Duration(seconds: 6));
    expect(synchronizer.loop?.enabled, isTrue);
  });

  for (final speed in [0.5, 1.0, 1.5]) {
    test('loop triggers at ${speed}x without scaling boundaries', () async {
      configureLoop();
      await synchronizer.setSpeed(speed);
      await synchronizer.play();

      player.emit(const Duration(seconds: 6));
      await pumpEventQueue();

      expect(player.seekCalls.last, const Duration(seconds: 2));
      expect(controller.position, const Duration(seconds: 2));
      expect(synchronizer.speed, speed);
      expect(synchronizer.status, PracticePlaybackStatus.playing);
    });
  }

  test('completion and replay preserve selected speed', () async {
    await synchronizer.setSpeed(1.5);
    await synchronizer.play();
    player.complete();
    await pumpEventQueue();
    expect(synchronizer.status, PracticePlaybackStatus.completed);

    await synchronizer.play();
    await pumpEventQueue();

    expect(controller.position, Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.playing);
    expect(synchronizer.speed, 1.5);
  });
}
