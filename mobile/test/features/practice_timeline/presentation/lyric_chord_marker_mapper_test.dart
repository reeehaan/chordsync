import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/presentation/lyric_chord_marker_mapper.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'each marker knows when its chord starts and when the next one does',
    () {
      final mapped = LyricChordMarkerMapper.map(
        _timeline(
          chords: const [(0.0, 'C'), (1.7, 'G'), (2.4, 'Am')],
          words: const [
            (1.0, 1.4, 'one'),
            (1.6, 2.0, 'two'),
            (2.1, 2.5, 'three'),
          ],
        ),
      );

      final spans = [for (final word in mapped) word.chordSpans];
      expect(spans[0].single.start, 0.0);
      expect(spans[0].single.end, 1.7);
      expect(spans[1].single.start, 1.7);
      expect(spans[1].single.end, 2.4);
      expect(spans[2].single.start, 2.4);
      expect(spans[2].single.end, double.infinity);
      expect(
        mapped.every(
          (word) => word.chordSpans.length == word.chordMarkers.length,
        ),
        isTrue,
      );
    },
  );

  test('a span says whether its chord is upcoming, playing or played', () {
    const span = ChordSpan(start: 2.0, end: 3.0);

    expect(span.isUpcoming(1.9), isTrue);
    expect(span.isPlaying(1.9), isFalse);
    expect(span.isPlaying(2.0), isTrue);
    expect(span.isPlaying(2.99), isTrue);
    expect(span.isPlaying(3.0), isFalse);
    expect(span.isUpcoming(3.5), isFalse);
  });

  test('one chord through several words creates one marker', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'C')],
        words: const [
          (1.0, 1.4, 'one'),
          (1.5, 2.0, 'two'),
          (2.1, 2.5, 'three'),
        ],
      ),
    );

    expect(mapped.map((word) => word.chordMarker).toList(), ['C', null, null]);
  });

  test('a chord change between words attaches to the following word', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'C'), (1.5, 'G')],
        words: const [(1.0, 1.4, 'one'), (1.6, 2.0, 'two')],
      ),
    );

    expect(mapped.map((word) => word.chordMarker).toList(), ['C', 'G']);
  });

  test('a chord change lands on the word already being sung', () {
    // G changes at 1.7, which is mid-word for "two" ([1.6, 2.0)): the
    // strummer is already singing "two" when the new chord starts, so the
    // marker belongs there, not on the next word "three".
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'C'), (1.7, 'G'), (2.7, 'Am')],
        words: const [
          (1.0, 1.4, 'one'),
          (1.6, 2.0, 'two'),
          (2.5, 3.0, 'three'),
          (3.0, 3.4, 'four'),
        ],
      ),
    );

    expect(mapped.map((word) => word.chordMarker).toList(), [
      'C',
      'G',
      'Am',
      null,
    ]);
  });

  test('adjacent identical chord labels do not duplicate a marker', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'C'), (1.0, 'C'), (2.0, 'G')],
        words: const [(0.5, 1.5, 'one'), (2.1, 2.4, 'two')],
      ),
    );

    expect(mapped.expand((word) => word.chordMarkers).toList(), ['C', 'G']);
  });

  test('a change during a lyric gap uses the next real word', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'C'), (2.0, 'G')],
        words: const [(1.0, 1.4, 'one'), (3.0, 3.4, 'two')],
      ),
    );

    expect(mapped, hasLength(2));
    expect(mapped.map((word) => word.chordMarker).toList(), ['C', 'G']);
  });

  test('no-chord changes do not clutter lyric markers', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'N'), (1.5, 'C')],
        words: const [(1.0, 1.4, 'one'), (1.6, 2.0, 'two')],
      ),
    );

    expect(mapped.map((word) => word.chordMarker).toList(), [null, 'C']);
  });

  test('a chord before the first lyric attaches to the first word', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.5, 'Dm')],
        words: const [(3.0, 3.4, 'one'), (3.5, 4.0, 'two')],
      ),
    );

    expect(mapped.map((word) => word.chordMarker).toList(), ['Dm', null]);
  });

  test(
    'only the active chord is shown when several changes precede lyrics',
    () {
      final mapped = LyricChordMarkerMapper.map(
        _timeline(
          chords: const [(0.0, 'C'), (1.0, 'G'), (2.0, 'Dm')],
          words: const [(3.0, 3.4, 'one'), (3.5, 4.0, 'two')],
        ),
      );

      expect(mapped.map((word) => word.chordMarker).toList(), ['Dm', null]);
    },
  );

  test('a mid-word chord change never attaches to a later word than the one '
      'sounding at that instant', () {
    // Regression for a bug where every chord that changed mid-word was
    // shown one lyric word later than where the strum actually happens.
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'Em'), (3.2, 'D')],
        words: const [(2.0, 4.0, 'looooong'), (4.5, 5.0, 'word')],
      ),
    );

    expect(mapped.map((word) => word.chordMarker).toList(), ['D', null]);
  });

  test('a chord after the final lyric creates no marker', () {
    final mapped = LyricChordMarkerMapper.map(
      _timeline(
        chords: const [(0.0, 'C'), (4.0, 'G')],
        words: const [(1.0, 1.4, 'one'), (1.5, 2.0, 'two')],
      ),
    );

    expect(mapped.expand((word) => word.chordMarkers).toList(), ['C']);
  });
}

SharedTimeline _timeline({
  required List<(double, String)> chords,
  required List<(double, double, String)> words,
}) {
  final end = [
    ...chords.map((event) => event.$1),
    ...words.map((word) => word.$2),
    1.0,
  ].reduce((left, right) => left > right ? left : right);
  return SharedTimeline(
    schemaVersion: 1,
    bpm: 120,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'test',
    bars: [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: end,
        beats: [
          for (var index = 0; index < chords.length; index++)
            TimelineEvent(
              time: chords[index].$1,
              beatNumber: (index % 4) + 1,
              isDownbeat: index % 4 == 0,
              chord: chords[index].$2,
            ),
        ],
      ),
    ],
    lyrics: [
      LyricSegment(
        start: words.isEmpty ? 0 : words.first.$1,
        end: words.isEmpty ? 0 : words.last.$2,
        text: words.map((word) => word.$3).join(' '),
        words: [
          for (final word in words)
            LyricWord(start: word.$1, end: word.$2, text: word.$3),
        ],
      ),
    ],
  );
}
