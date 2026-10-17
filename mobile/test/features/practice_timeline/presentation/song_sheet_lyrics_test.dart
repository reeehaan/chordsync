import 'package:chordsync/features/practice_timeline/data/chord_transposition.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/presentation/lyric_chord_marker_mapper.dart';
import 'package:chordsync/features/practice_timeline/presentation/lyric_display_block.dart';
import 'package:chordsync/features/practice_timeline/presentation/practice_stage_colors.dart';
import 'package:chordsync/features/practice_timeline/presentation/song_sheet_lyrics.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('groups words naturally and keeps inline chords anchored', (
    tester,
  ) async {
    final timeline = _singleSegmentTimeline();
    final blocks = LyricDisplayBlockGrouper.group(
      LyricChordMarkerMapper.map(timeline),
    );

    expect(blocks, hasLength(3));
    expect(blocks.expand((block) => block.words), hasLength(9));
    expect(
      blocks.expand((block) => block.words).map((entry) => entry.word.text),
      [
        'Sing',
        'this',
        'line.',
        'Then',
        'wait',
        'for',
        'another',
        'short',
        'line',
      ],
    );

    await _pumpLyrics(tester, timeline, 1.2);
    expect(find.byKey(const ValueKey('inlineChord0_0_0')), findsOneWidget);
    expect(find.byKey(const ValueKey('inlineChord0_3_0')), findsOneWidget);
    expect(find.byKey(const ValueKey('segmentChord0')), findsNothing);
    const cellHeight =
        SongSheetLyrics.chordLaneHeight + SongSheetLyrics.wordLineHeight;
    final firstRow = tester.getSize(find.byKey(const ValueKey('lyricRow0')));
    expect(firstRow.height, cellHeight);
    final firstCell = tester.getSize(
      find.byKey(const ValueKey('lyricWordCell0_0')),
    );
    expect(firstCell.height, cellHeight);
    final wordStyles = <AnimatedDefaultTextStyle>[
      for (final start in const [0.5, 1.5, 2.5])
        tester.widget<AnimatedDefaultTextStyle>(
          find.byKey(ValueKey('sheetWordStyle$start')),
        ),
    ];
    expect(wordStyles.map((word) => word.style.fontSize).toSet(), {19.0});
    expect(tester.takeException(), isNull);
  });

  testWidgets('sizes each word to its own text so none overlap', (
    tester,
  ) async {
    // Mixed short and very long words in one line: the previous equal-width
    // layout made the long ones paint over their neighbours.
    final timeline = _unevenWordTimeline();
    await _pumpLyrics(tester, timeline, 0.6);

    final rects = <Rect>[
      for (var index = 0; index < 5; index++)
        tester.getRect(find.byKey(ValueKey('lyricWordCell0_$index'))),
    ];

    for (var index = 0; index + 1 < rects.length; index++) {
      final left = rects[index];
      final right = rects[index + 1];
      if (left.top != right.top) continue; // wrapped onto the next run
      expect(
        left.right,
        lessThanOrEqualTo(right.left),
        reason: 'word $index overlaps word ${index + 1}',
      );
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('keeps one uniform row height for even line spacing', (
    tester,
  ) async {
    final timeline = _multiBlockTimeline();
    await _pumpLyrics(tester, timeline, 0.6);

    final tops = <double>[
      for (var index = 0; index < 3; index++)
        tester.getTopLeft(find.byKey(ValueKey('lyricBlock$index'))).dy,
    ];

    expect(tops[1] - tops[0], SongSheetLyrics.blockExtent);
    expect(tops[2] - tops[1], SongSheetLyrics.blockExtent);
  });

  testWidgets('auto-follows only when the focused lyric block changes', (
    tester,
  ) async {
    final timeline = _multiBlockTimeline();
    await _pumpLyrics(tester, timeline, 0.6);
    final list = tester.widget<ListView>(
      find.byKey(const ValueKey('lyricScrollView')),
    );
    expect(list.controller!.offset, 0);

    await _pumpLyrics(tester, timeline, 20.6, settle: false);
    await tester.pumpAndSettle();

    expect(list.controller!.offset, greaterThan(0));
    expect(find.byKey(const ValueKey('currentLyricBlock')), findsOneWidget);
    final active = tester.widget<AnimatedDefaultTextStyle>(
      find.byKey(const ValueKey('sheetWordStyle20.5')),
    );
    expect(active.style.color, PracticeStageColors.amberBright);
    expect(active.duration, const Duration(milliseconds: 180));
  });

  testWidgets('keeps following when the timeline is rebuilt on every frame', (
    tester,
  ) async {
    // With a capo set the practice screen hands over a new timeline object on
    // every build; following must not depend on the object staying the same.
    final source = _multiBlockTimeline();
    await _pumpLyrics(
      tester,
      ChordTransposition.timelineForCapo(source, 2),
      0.6,
    );
    final list = tester.widget<ListView>(
      find.byKey(const ValueKey('lyricScrollView')),
    );
    expect(list.controller!.offset, 0);

    for (final time in [8.6, 14.6, 20.6, 26.6]) {
      await _pumpLyrics(
        tester,
        ChordTransposition.timelineForCapo(source, 2),
        time,
        settle: false,
      );
      await tester.pumpAndSettle();
    }

    expect(list.controller!.offset, greaterThan(0));
    expect(find.byKey(const ValueKey('currentLyricBlock')), findsOneWidget);
  });

  testWidgets('manual scrolling suspends follow until Follow is tapped', (
    tester,
  ) async {
    final timeline = _multiBlockTimeline();
    await _pumpLyrics(tester, timeline, 8.6);
    final scrollView = find.byKey(const ValueKey('lyricScrollView'));
    final list = tester.widget<ListView>(scrollView);

    await tester.drag(scrollView, const Offset(0, -120));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('followLyricsButton')), findsOneWidget);
    final manualOffset = list.controller!.offset;

    await _pumpLyrics(tester, timeline, 28.6, settle: false);
    await tester.pump(const Duration(milliseconds: 400));
    expect(list.controller!.offset, closeTo(manualOffset, 0.1));

    await tester.tap(find.byKey(const ValueKey('followLyricsButton')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('followLyricsButton')), findsNothing);
    expect(list.controller!.offset, isNot(closeTo(manualOffset, 0.1)));
  });
}

Future<void> _pumpLyrics(
  WidgetTester tester,
  SharedTimeline timeline,
  double playbackTime, {
  bool settle = true,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Center(
          child: SizedBox(
            width: 390,
            height: 280,
            child: SongSheetLyrics(
              timeline: timeline,
              playbackTime: playbackTime,
            ),
          ),
        ),
      ),
    ),
  );
  if (settle) await tester.pumpAndSettle();
}

SharedTimeline _singleSegmentTimeline() {
  const words = [
    LyricWord(start: 0.5, end: 1.3, text: 'Sing'),
    LyricWord(start: 1.5, end: 2.3, text: 'this'),
    LyricWord(start: 2.5, end: 3.3, text: 'line.'),
    LyricWord(start: 3.5, end: 4.3, text: 'Then'),
    LyricWord(start: 4.5, end: 5.3, text: 'wait'),
    LyricWord(start: 6.5, end: 7.3, text: 'for'),
    LyricWord(start: 7.5, end: 8.3, text: 'another'),
    LyricWord(start: 8.5, end: 9.3, text: 'short'),
    LyricWord(start: 9.5, end: 10.3, text: 'line'),
  ];
  return const SharedTimeline(
    schemaVersion: 1,
    bpm: 120,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'test',
    bars: [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 11,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
          TimelineEvent(
            time: 3.4,
            beatNumber: 2,
            isDownbeat: false,
            chord: 'G',
          ),
          TimelineEvent(
            time: 6.4,
            beatNumber: 3,
            isDownbeat: false,
            chord: 'Am',
          ),
        ],
      ),
    ],
    lyrics: [LyricSegment(start: 0.5, end: 10.3, text: 'source', words: words)],
  );
}

SharedTimeline _unevenWordTimeline() {
  const words = [
    LyricWord(start: 0.5, end: 1.3, text: 'I'),
    LyricWord(start: 1.5, end: 2.3, text: 'overwhelmingly'),
    LyricWord(start: 2.5, end: 3.3, text: 'a'),
    LyricWord(start: 3.5, end: 4.3, text: 'disproportionate'),
    LyricWord(start: 4.5, end: 5.3, text: 'it'),
  ];
  return const SharedTimeline(
    schemaVersion: 1,
    bpm: 120,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'test',
    bars: [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 6,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
          TimelineEvent(
            time: 2.4,
            beatNumber: 2,
            isDownbeat: false,
            chord: 'G',
          ),
        ],
      ),
    ],
    lyrics: [LyricSegment(start: 0.5, end: 5.3, text: 'source', words: words)],
  );
}

SharedTimeline _multiBlockTimeline() {
  return SharedTimeline(
    schemaVersion: 1,
    bpm: 120,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'test',
    bars: const [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 32,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
          TimelineEvent(time: 8, beatNumber: 2, isDownbeat: false, chord: 'G'),
          TimelineEvent(
            time: 16,
            beatNumber: 3,
            isDownbeat: false,
            chord: 'Am',
          ),
          TimelineEvent(time: 24, beatNumber: 4, isDownbeat: false, chord: 'F'),
        ],
      ),
    ],
    lyrics: [
      for (var block = 0; block < 8; block++)
        LyricSegment(
          start: block * 4 + 0.5,
          end: block * 4 + 3.3,
          text: 'line $block words',
          words: [
            for (var word = 0; word < 3; word++)
              LyricWord(
                start: block * 4 + word + 0.5,
                end: block * 4 + word + 1.3,
                text: 'line${block}word$word',
              ),
          ],
        ),
    ],
  );
}
