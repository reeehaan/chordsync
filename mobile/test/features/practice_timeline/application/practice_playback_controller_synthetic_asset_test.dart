import 'package:chordsync/features/practice_timeline/application/practice_playback_controller.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'supports forward and backward seeking on the synthetic asset',
    () async {
      final timeline = await SharedTimelineAssetLoader.load();
      final controller = PracticePlaybackController(timeline);

      expect(controller.state.playbackTime, 0);
      expect(controller.state.chord, 'N');
      expect(controller.state.beatNumber, isNull);
      expect(controller.state.isDownbeat, isFalse);
      expect(controller.state.lyricWord, isNull);

      controller.setPosition(const Duration(seconds: 1));
      expect(controller.state.chord, 'C');
      expect(controller.state.beatNumber, 1);
      expect(controller.state.isDownbeat, isTrue);
      expect(controller.state.lyricWord, isNull);

      controller.setPosition(const Duration(seconds: 2));
      expect(controller.state.chord, 'G');
      expect(controller.state.beatNumber, 2);
      expect(controller.state.isDownbeat, isFalse);
      expect(controller.state.lyricWord, 'Morning');

      controller.setPosition(const Duration(milliseconds: 3500));
      expect(controller.state.chord, 'Am');
      expect(controller.state.beatNumber, 3);
      expect(controller.state.lyricWord, 'moves');

      controller.setPosition(const Duration(seconds: 4));
      expect(controller.state.chord, 'F');
      expect(controller.state.beatNumber, 4);
      expect(controller.state.lyricWord, isNull);

      controller.setPosition(const Duration(seconds: 6));
      expect(controller.state.chord, 'G');
      expect(controller.state.beatNumber, 2);
      expect(controller.state.lyricWord, 'open');

      controller.setPosition(const Duration(seconds: 2));
      expect(controller.state.chord, 'G');
      expect(controller.state.beatNumber, 2);
      expect(controller.state.lyricWord, 'Morning');
    },
  );
}
