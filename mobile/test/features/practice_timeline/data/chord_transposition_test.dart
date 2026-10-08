import 'package:chordsync/features/practice_timeline/data/chord_transposition.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const timeline = SharedTimeline(
    schemaVersion: 1,
    bpm: 92,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'test',
    bars: [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 4,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'A#'),
          TimelineEvent(time: 1, beatNumber: 2, isDownbeat: false, chord: 'G#'),
          TimelineEvent(
            time: 2,
            beatNumber: 3,
            isDownbeat: false,
            chord: 'A#m',
          ),
        ],
      ),
    ],
    lyrics: [],
  );

  test('capo one converts sharp barre shapes without changing quality', () {
    expect(ChordTransposition.forCapo('A#', 1), 'A');
    expect(ChordTransposition.forCapo('G#', 1), 'G');
    expect(ChordTransposition.forCapo('A#m', 1), 'Am');
    expect(ChordTransposition.forCapo('N', 1), 'N');
  });

  test('recommends one song-wide capo for A-sharp and G-sharp song', () {
    expect(ChordTransposition.recommendedCapo(timeline), 1);
    expect(ChordTransposition.songChords(timeline, capoFret: 1), [
      'A',
      'G',
      'Am',
    ]);
  });

  test('display timeline preserves timing and the analyzed timeline', () {
    final displayed = ChordTransposition.timelineForCapo(timeline, 1);
    expect(displayed.bars.first.beats.first.chord, 'A');
    expect(displayed.bars.first.beats.first.time, 0);
    expect(timeline.bars.first.beats.first.chord, 'A#');
  });
}
