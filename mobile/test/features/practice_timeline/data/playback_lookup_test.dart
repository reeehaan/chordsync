import 'package:chordsync/features/practice_timeline/data/playback_lookup.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'currentBeat returns the most recent beat at or before playback time',
    () {
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
            endTime: 3,
            beats: [
              TimelineEvent(
                time: 1,
                beatNumber: 1,
                isDownbeat: true,
                chord: 'C',
              ),
              TimelineEvent(
                time: 2,
                beatNumber: 2,
                isDownbeat: false,
                chord: 'G',
              ),
            ],
          ),
        ],
        lyrics: [],
      );

      expect(PlaybackLookup.currentBeat(timeline, 2.5)?.chord, 'G');
      expect(PlaybackLookup.currentBeat(timeline, 2)?.beatNumber, 2);
    },
  );

  test(
    'activeLyricWord is present only from start inclusive to end exclusive',
    () {
      const timeline = SharedTimeline(
        schemaVersion: 1,
        bpm: 120,
        beatsPerBar: 4,
        beatSource: 'test',
        lyricSource: 'test',
        bars: [],
        lyrics: [
          LyricSegment(
            start: 1,
            end: 4,
            text: 'Hello world',
            words: [
              LyricWord(start: 1, end: 2, text: 'Hello'),
              LyricWord(start: 3, end: 4, text: 'world'),
            ],
          ),
        ],
      );

      expect(PlaybackLookup.activeLyricWord(timeline, 1)?.text, 'Hello');
      expect(PlaybackLookup.activeLyricWord(timeline, 2), isNull);
      expect(PlaybackLookup.activeLyricWord(timeline, 2.5), isNull);
      expect(PlaybackLookup.activeLyricWord(timeline, 3)?.text, 'world');
      expect(PlaybackLookup.activeLyricWord(timeline, 4), isNull);
    },
  );

  test('playbackState safely represents playback before the first beat', () {
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
          endTime: 2,
          beats: [
            TimelineEvent(time: 1, beatNumber: 1, isDownbeat: true, chord: 'C'),
          ],
        ),
      ],
      lyrics: [],
    );

    final state = PlaybackLookup.playbackState(timeline, 0.5);

    expect(state.playbackTime, 0.5);
    expect(state.chord, 'N');
    expect(state.beatNumber, isNull);
    expect(state.isDownbeat, isFalse);
    expect(state.lyricWord, isNull);
  });
}
