import 'package:chordsync/features/practice_timeline/data/playback_lookup.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'resolves chord and lyric context across the synthetic timeline',
    () async {
      final timeline = await SharedTimelineAssetLoader.load();

      final beforeFirstEvent = PlaybackLookup.playbackState(timeline, 0);
      expect(beforeFirstEvent.currentChord, 'N');
      expect(beforeFirstEvent.nextChord, 'C');
      expect(beforeFirstEvent.previousLyricWord, isNull);
      expect(beforeFirstEvent.activeLyricWord, isNull);
      expect(beforeFirstEvent.nextLyricWord, 'Morning');

      final atChordChange = PlaybackLookup.playbackState(timeline, 2);
      expect(atChordChange.currentChord, 'G');
      expect(atChordChange.nextChord, 'Am');

      final activeWord = PlaybackLookup.playbackState(timeline, 3.2);
      expect(activeWord.previousLyricWord, 'light');
      expect(activeWord.activeLyricWord, 'moves');
      expect(activeWord.nextLyricWord, 'across');

      final lyricGap = PlaybackLookup.playbackState(timeline, 5.65);
      expect(lyricGap.previousLyricWord, 'the');
      expect(lyricGap.activeLyricWord, isNull);
      expect(lyricGap.nextLyricWord, 'open');

      final afterFinalLyric = PlaybackLookup.playbackState(timeline, 8);
      expect(afterFinalLyric.previousLyricWord, 'glows');
      expect(afterFinalLyric.activeLyricWord, isNull);
      expect(afterFinalLyric.nextLyricWord, isNull);
      expect(afterFinalLyric.nextChord, isNull);

      final atTimelineEnd = PlaybackLookup.playbackState(timeline, 9);
      expect(atTimelineEnd.nextChord, isNull);
    },
  );

  test('next chord skips repeated events with the current chord', () {
    const timeline = SharedTimeline(
      schemaVersion: 1,
      bpm: 120,
      beatsPerBar: 4,
      beatSource: 'test',
      lyricSource: 'test',
      bars: [
        TimelineBar(
          barNumber: 1,
          startTime: 1,
          endTime: 4,
          beats: [
            TimelineEvent(time: 1, beatNumber: 1, isDownbeat: true, chord: 'C'),
            TimelineEvent(
              time: 2,
              beatNumber: 2,
              isDownbeat: false,
              chord: 'C',
            ),
            TimelineEvent(
              time: 3,
              beatNumber: 3,
              isDownbeat: false,
              chord: 'G',
            ),
          ],
        ),
      ],
      lyrics: [],
    );

    final activeFirstChord = PlaybackLookup.playbackState(timeline, 1);
    expect(activeFirstChord.currentChord, 'C');
    expect(activeFirstChord.nextChord, 'G');
  });
}
