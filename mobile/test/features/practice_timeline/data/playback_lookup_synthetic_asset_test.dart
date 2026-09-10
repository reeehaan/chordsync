import 'package:chordsync/features/practice_timeline/data/playback_lookup.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('resolves known playback states from the synthetic asset', () async {
    final timeline = await SharedTimelineAssetLoader.load();

    final beforeFirstBeat = PlaybackLookup.playbackState(timeline, 0);
    expect(beforeFirstBeat.chord, 'N');
    expect(beforeFirstBeat.beatNumber, isNull);
    expect(beforeFirstBeat.isDownbeat, isFalse);
    expect(beforeFirstBeat.lyricWord, isNull);

    final atOne = PlaybackLookup.playbackState(timeline, 1);
    expect(atOne.chord, 'C');
    expect(atOne.beatNumber, 1);
    expect(atOne.isDownbeat, isTrue);
    expect(atOne.lyricWord, isNull);

    final atTwo = PlaybackLookup.playbackState(timeline, 2);
    expect(atTwo.chord, 'G');
    expect(atTwo.beatNumber, 2);
    expect(atTwo.isDownbeat, isFalse);
    expect(atTwo.lyricWord, 'Morning');

    final atThreePointFive = PlaybackLookup.playbackState(timeline, 3.5);
    expect(atThreePointFive.chord, 'Am');
    expect(atThreePointFive.beatNumber, 3);
    expect(atThreePointFive.isDownbeat, isFalse);
    expect(atThreePointFive.lyricWord, 'moves');

    final inLyricGap = PlaybackLookup.playbackState(timeline, 4);
    expect(inLyricGap.chord, 'F');
    expect(inLyricGap.beatNumber, 4);
    expect(inLyricGap.isDownbeat, isFalse);
    expect(inLyricGap.lyricWord, isNull);

    final atSix = PlaybackLookup.playbackState(timeline, 6);
    expect(atSix.chord, 'G');
    expect(atSix.beatNumber, 2);
    expect(atSix.isDownbeat, isFalse);
    expect(atSix.lyricWord, 'open');
  });
}
