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

  test(
    'next and previous navigation seek to actual bar starts while paused',
    () async {
      expect(synchronizer.canSeekToPreviousBar, isFalse);
      expect(synchronizer.canSeekToNextBar, isTrue);
      expect(await synchronizer.seekToPreviousBar(), isFalse);
      expect(player.seekCalls, isEmpty);

      expect(await synchronizer.seekToNextBar(), isTrue);
      await pumpEventQueue();
      expect(player.seekCalls.last, const Duration(seconds: 1));
      expect(controller.position, const Duration(seconds: 1));
      expect(synchronizer.status, PracticePlaybackStatus.paused);

      await synchronizer.seek(const Duration(seconds: 3));
      await pumpEventQueue();
      expect(await synchronizer.seekToPreviousBar(), isTrue);
      await pumpEventQueue();
      expect(player.seekCalls.last, const Duration(seconds: 1));

      expect(await synchronizer.seekToNextBar(), isTrue);
      await pumpEventQueue();
      expect(player.seekCalls.last, const Duration(seconds: 5));
      expect(controller.state.currentBarNumber, 2);
      expect(controller.state.beatNumber, 1);
      expect(synchronizer.status, PracticePlaybackStatus.paused);
    },
  );

  test('bar navigation preserves playing state and selected speed', () async {
    await synchronizer.seek(const Duration(seconds: 3));
    await synchronizer.setSpeed(1.5);
    await synchronizer.play();
    await pumpEventQueue();

    expect(await synchronizer.seekToNextBar(), isTrue);
    await pumpEventQueue();

    expect(controller.position, const Duration(seconds: 5));
    expect(synchronizer.status, PracticePlaybackStatus.playing);
    expect(synchronizer.speed, 1.5);
  });

  for (final speed in [0.5, 1.0, 1.5]) {
    test('navigation target remains media time at ${speed}x', () async {
      await synchronizer.seek(const Duration(seconds: 3));
      await synchronizer.setSpeed(speed);
      await pumpEventQueue();

      expect(await synchronizer.seekToNextBar(), isTrue);
      await pumpEventQueue();
      expect(player.seekCalls.last, const Duration(seconds: 5));
      expect(synchronizer.speed, speed);
    });
  }

  test('manual bar navigation is respected outside an enabled loop', () async {
    synchronizer.setLoopStart(const Duration(seconds: 2));
    synchronizer.setLoopEnd(const Duration(seconds: 4));
    synchronizer.enableLoop();

    expect(await synchronizer.seekToNextBar(), isTrue);
    await pumpEventQueue();
    expect(controller.position, const Duration(seconds: 1));
    expect(synchronizer.loop?.start, const Duration(seconds: 2));
    expect(synchronizer.loop?.end, const Duration(seconds: 4));

    expect(await synchronizer.seekToNextBar(), isTrue);
    await pumpEventQueue();
    expect(controller.position, const Duration(seconds: 5));
    expect(synchronizer.loop?.start, const Duration(seconds: 2));
    expect(synchronizer.loop?.end, const Duration(seconds: 4));
  });

  test(
    'completion can navigate to final bar start and leaves playback paused',
    () async {
      player.complete();
      await pumpEventQueue();
      expect(synchronizer.status, PracticePlaybackStatus.completed);

      expect(await synchronizer.seekToPreviousBar(), isTrue);
      await pumpEventQueue();

      expect(controller.position, const Duration(seconds: 5));
      expect(synchronizer.status, PracticePlaybackStatus.paused);
      expect(synchronizer.canSeekToNextBar, isFalse);
    },
  );

  test('disposal still removes position and status subscriptions', () async {
    await synchronizer.dispose();
    expect(player.hasPositionListener, isFalse);
    expect(player.hasStatusListener, isFalse);
  });
}
