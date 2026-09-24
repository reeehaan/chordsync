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
    expect(tester.takeException(), isNull);
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
