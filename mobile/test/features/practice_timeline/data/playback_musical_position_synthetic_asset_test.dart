import 'package:chordsync/features/practice_timeline/data/playback_lookup.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'resolves bar, beat, and progression across the synthetic timeline',
    () async {
      final timeline = await SharedTimelineAssetLoader.load();

      final beforeFirstBar = PlaybackLookup.playbackState(timeline, 0);
      expect(beforeFirstBar.currentBarNumber, isNull);
      expect(beforeFirstBar.beatNumber, isNull);
      expect(beforeFirstBar.beatsPerBar, 4);
      expect(beforeFirstBar.chordProgression, ['C', 'G', 'Am', 'F']);

      final firstBeat = PlaybackLookup.playbackState(timeline, 1);
      expect(firstBeat.currentBarNumber, 1);
      expect(firstBeat.beatNumber, 1);
      expect(firstBeat.beatsPerBar, 4);
      expect(firstBeat.chordProgression, ['C', 'G', 'Am', 'F']);

      final middleOfFirstBar = PlaybackLookup.playbackState(timeline, 3.5);
      expect(middleOfFirstBar.currentBarNumber, 1);
      expect(middleOfFirstBar.beatNumber, 3);
      expect(middleOfFirstBar.chordProgression, ['Am', 'F', 'Dm', 'G']);

      final secondBarBoundary = PlaybackLookup.playbackState(timeline, 5);
      expect(secondBarBoundary.currentBarNumber, 2);
      expect(secondBarBoundary.beatNumber, 1);
      expect(secondBarBoundary.chordProgression, ['Dm', 'G', 'C']);

      final nearEnd = PlaybackLookup.playbackState(timeline, 8);
      expect(nearEnd.currentBarNumber, 2);
      expect(nearEnd.beatNumber, 4);
      expect(nearEnd.chordProgression, ['C']);

      final atCompletion = PlaybackLookup.playbackState(timeline, 9);
      expect(atCompletion.currentBarNumber, 2);
      expect(atCompletion.beatNumber, 4);
      expect(atCompletion.chordProgression, ['C']);
    },
  );

  test('progression is bounded and skips repeated chord beats', () {
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
          endTime: 6,
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
            TimelineEvent(
              time: 4,
              beatNumber: 4,
              isDownbeat: false,
              chord: 'G',
            ),
            TimelineEvent(
              time: 5,
              beatNumber: 1,
              isDownbeat: true,
              chord: 'Am',
            ),
          ],
        ),
      ],
      lyrics: [],
    );

    expect(PlaybackLookup.chordProgression(timeline, 1), ['C', 'G', 'Am']);
    expect(PlaybackLookup.chordProgression(timeline, 0, limit: 2), ['C', 'G']);
  });
}
