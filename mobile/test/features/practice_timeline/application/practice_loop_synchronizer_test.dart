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

  void configureLoop({
    Duration start = const Duration(seconds: 2),
    Duration end = const Duration(seconds: 6),
  }) {
    expect(synchronizer.setLoopStart(start), isTrue);
    expect(synchronizer.setLoopEnd(end), isTrue);
  }

  test('configures a valid loop and rejects invalid updates', () {
    configureLoop();
    expect(synchronizer.loop?.start, const Duration(seconds: 2));
    expect(synchronizer.loop?.end, const Duration(seconds: 6));
    expect(synchronizer.loop?.enabled, isFalse);

    expect(synchronizer.setLoopEnd(const Duration(seconds: 2)), isFalse);
    expect(synchronizer.setLoopEnd(const Duration(seconds: 10)), isFalse);
    expect(synchronizer.setLoopStart(const Duration(seconds: -1)), isFalse);
    expect(synchronizer.setLoopStart(const Duration(seconds: 6)), isFalse);
    expect(synchronizer.loop?.start, const Duration(seconds: 2));
    expect(synchronizer.loop?.end, const Duration(seconds: 6));
  });

  test('loops exactly at and beyond B while playback continues', () async {
    configureLoop();
    expect(synchronizer.enableLoop(), isTrue);
    await synchronizer.play();

    player.emit(const Duration(milliseconds: 5999));
    await pumpEventQueue();
    expect(player.seekCalls, isEmpty);

    player.emit(const Duration(seconds: 6));
    await pumpEventQueue();
    expect(player.seekCalls.last, const Duration(seconds: 2));
    expect(controller.position, const Duration(seconds: 2));
    expect(synchronizer.status, PracticePlaybackStatus.playing);

    player.emit(const Duration(seconds: 7));
    await pumpEventQueue();
    expect(player.seekCalls.last, const Duration(seconds: 2));
    expect(player.seekCalls.length, 2);
    expect(controller.position, const Duration(seconds: 2));
  });

  test('paused loop configuration survives toggles and can be cleared', () {
    configureLoop();
    expect(synchronizer.status, PracticePlaybackStatus.paused);
    expect(synchronizer.enableLoop(), isTrue);
    synchronizer.disableLoop();
    expect(synchronizer.loop?.enabled, isFalse);
    expect(synchronizer.loop?.start, const Duration(seconds: 2));
    expect(synchronizer.loop?.end, const Duration(seconds: 6));
    expect(synchronizer.enableLoop(), isTrue);
    synchronizer.clearLoop();
    expect(synchronizer.loop, isNull);
    expect(synchronizer.loopStart, isNull);
    expect(synchronizer.enableLoop(), isFalse);
  });

  test('manual seek beyond B is respected until playback advances', () async {
    configureLoop();
    synchronizer.enableLoop();

    await synchronizer.seek(const Duration(seconds: 4));
    await pumpEventQueue();
    expect(controller.position, const Duration(seconds: 4));

    await synchronizer.seek(const Duration(seconds: 1));
    await pumpEventQueue();
    expect(controller.position, const Duration(seconds: 1));

    await synchronizer.seek(const Duration(seconds: 7));
    await pumpEventQueue();
    expect(controller.position, const Duration(seconds: 7));
    expect(player.seekCalls, [
      const Duration(seconds: 4),
      const Duration(seconds: 1),
      const Duration(seconds: 7),
    ]);

    await synchronizer.play();
    player.emit(const Duration(milliseconds: 7100));
    await pumpEventQueue();
    expect(player.seekCalls.last, const Duration(seconds: 2));
    expect(controller.position, const Duration(seconds: 2));
  });

  test('disabling loop restores normal position progression', () async {
    configureLoop();
    synchronizer.enableLoop();
    synchronizer.disableLoop();

    player.emit(const Duration(seconds: 7));
    await pumpEventQueue();
    expect(player.seekCalls, isEmpty);
    expect(controller.position, const Duration(seconds: 7));
  });

  test('loop ending at track duration overrides completion', () async {
    configureLoop(end: const Duration(seconds: 9));
    synchronizer.enableLoop();
    await synchronizer.play();

    player.complete();
    await pumpEventQueue();

    expect(player.seekCalls.last, const Duration(seconds: 2));
    expect(controller.position, const Duration(seconds: 2));
    expect(synchronizer.status, PracticePlaybackStatus.playing);
  });

  test('disposal removes audio subscriptions with a configured loop', () async {
    configureLoop();
    synchronizer.enableLoop();

    await synchronizer.dispose();

    expect(player.hasPositionListener, isFalse);
    expect(player.hasStatusListener, isFalse);
  });
}
