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
    await Future<void>.delayed(Duration.zero);
  });

  tearDown(() async {
    if (!player.disposed) await synchronizer.dispose();
  });

  test('starts paused at position zero', () {
    expect(synchronizer.status, PracticePlaybackStatus.paused);
    expect(controller.position, Duration.zero);
    expect(controller.state.chord, 'N');
  });

  test('plays, pauses, and resumes without resetting position', () async {
    await synchronizer.play();
    await Future<void>.delayed(Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.playing);

    player.emit(const Duration(seconds: 2));
    await Future<void>.delayed(Duration.zero);
    await synchronizer.pause();
    await Future<void>.delayed(Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.paused);
    expect(controller.position, const Duration(seconds: 2));

    await synchronizer.play();
    await Future<void>.delayed(Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.playing);
    expect(controller.position, const Duration(seconds: 2));
  });

  test('completion retains the final timeline state', () async {
    player.complete();
    await Future<void>.delayed(Duration.zero);

    expect(synchronizer.status, PracticePlaybackStatus.completed);
    expect(controller.position, const Duration(seconds: 9));
    expect(controller.state.chord, 'C');
    expect(controller.state.beatNumber, 4);
    expect(controller.state.lyricWord, isNull);
  });

  test('play after completion replays from zero', () async {
    player.complete();
    await Future<void>.delayed(Duration.zero);

    await synchronizer.play();
    await Future<void>.delayed(Duration.zero);

    expect(player.seekCalls.last, Duration.zero);
    expect(controller.position, Duration.zero);
    expect(controller.state.chord, 'N');
    expect(synchronizer.status, PracticePlaybackStatus.playing);
  });

  test('seeks while paused and playing, including backward and end', () async {
    await synchronizer.seek(const Duration(seconds: 6));
    await Future<void>.delayed(Duration.zero);
    expect(player.seekCalls.last, const Duration(seconds: 6));
    expect(synchronizer.status, PracticePlaybackStatus.paused);
    expect(controller.state.chord, 'G');
    expect(controller.state.lyricWord, 'open');

    await synchronizer.play();
    await synchronizer.seek(const Duration(seconds: 3));
    await Future<void>.delayed(Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.playing);
    expect(controller.state.chord, 'Am');

    await synchronizer.seek(const Duration(seconds: 9));
    await Future<void>.delayed(Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.completed);
    expect(controller.position, const Duration(seconds: 9));

    await synchronizer.seek(const Duration(seconds: 1));
    await Future<void>.delayed(Duration.zero);
    expect(synchronizer.status, PracticePlaybackStatus.paused);
    expect(controller.state.chord, 'C');
    expect(controller.state.beatNumber, 1);
  });

  test('disposal cancels position and status subscriptions', () async {
    expect(player.hasPositionListener, isTrue);
    expect(player.hasStatusListener, isTrue);

    await synchronizer.dispose();

    expect(player.disposed, isTrue);
    expect(player.hasPositionListener, isFalse);
    expect(player.hasStatusListener, isFalse);
  });
}
