import 'package:chordsync/features/practice_timeline/data/playback_state.dart';
import 'package:chordsync/features/practice_timeline/presentation/chord_diagram_strip.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _song = ['Em', 'G', 'D', 'C', 'Am', 'Bm', 'Gm', 'Em', 'G'];

Widget _strip({required bool beforePlay}) => MaterialApp(
  home: Scaffold(
    body: ChordDiagramStrip(
      previousChord: null,
      currentChord: 'Em',
      nextChord: 'G',
      progression: beforePlay ? _song : const ['Em', 'G', 'D'],
      chordProgress: beforePlay ? null : 0.3,
      chordStart: 0,
      showAllChords: beforePlay,
    ),
  ),
);

Widget _beatStrip(int beats, double playbackTime) => MaterialApp(
  home: Scaffold(
    body: ChordDiagramStrip(
      previousChord: null,
      currentChord: 'Em',
      nextChord: 'G',
      progression: const ['Em', 'G', 'D'],
      chordProgress: 0.3,
      chordStart: 0,
      chordBeats: [
        for (var beat = 0; beat < beats; beat++)
          ChordBeat(
            start: beat.toDouble(),
            end: beat + 1.0,
            isDownbeat: beat == 0,
          ),
      ],
      playbackTime: playbackTime,
    ),
  ),
);

void main() {
  testWidgets('a chord shows one segment per beat, filled as it plays', (
    tester,
  ) async {
    await tester.pumpWidget(_beatStrip(4, 1.5));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('chordBeatSegments')), findsOneWidget);
    expect(find.byKey(const ValueKey('chordProgressBar')), findsNothing);
    double fill(int index) => tester
        .widget<FractionallySizedBox>(
          find.descendant(
            of: find.byKey(ValueKey('beatSegment$index')),
            matching: find.byType(FractionallySizedBox),
          ),
        )
        .widthFactor!;
    expect(find.byKey(const ValueKey('beatSegment3')), findsOneWidget);
    expect(find.byKey(const ValueKey('beatSegment4')), findsNothing);
    expect(fill(0), 1);
    expect(fill(1), closeTo(0.5, 0.001));
    expect(fill(2), 0);
    // Every segment is the same height, including the one that opens a bar.
    final heights = {
      for (var index = 0; index < 4; index++)
        tester.getSize(find.byKey(ValueKey('beatSegment$index'))).height,
    };
    expect(heights, hasLength(1));
  });

  testWidgets('a very long chord keeps the plain progress bar', (tester) async {
    await tester.pumpWidget(_beatStrip(12, 1.5));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('chordBeatSegments')), findsNothing);
    expect(find.byKey(const ValueKey('chordProgressBar')), findsOneWidget);
  });

  testWidgets('before playing every chord of the song shows once, in order', (
    tester,
  ) async {
    await tester.pumpWidget(_strip(beforePlay: true));
    await tester.pumpAndSettle();

    final strip = find.byKey(const ValueKey('songChordDiagramStrip'));
    expect(strip, findsOneWidget);
    // No chord is raised and no progress bar runs yet.
    expect(find.byKey(const ValueKey('chordProgressBar')), findsNothing);
    final labels = tester
        .widgetList<Text>(
          find.descendant(of: strip, matching: find.byType(Text)),
        )
        .map((text) => text.data)
        .toList();
    expect(labels, ['Em', 'G', 'D', 'C', 'Am', 'Bm', 'Gm']);
  });

  testWidgets('the song row scrolls sideways when it does not fit', (
    tester,
  ) async {
    await tester.pumpWidget(_strip(beforePlay: true));
    await tester.pumpAndSettle();

    final before = tester.getTopLeft(find.text('Gm')).dx;
    expect(before, greaterThan(400)); // off the right edge of the screen
    await tester.drag(
      find.byKey(const ValueKey('songChordDiagramStrip')),
      const Offset(-600, 0),
    );
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('Gm')).dx, lessThan(before));
  });

  testWidgets('pressing play swaps to the moving chord bar', (tester) async {
    await tester.pumpWidget(_strip(beforePlay: true));
    await tester.pumpAndSettle();

    await tester.pumpWidget(_strip(beforePlay: false));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('songChordDiagramStrip')), findsNothing);
    expect(
      find.byKey(const ValueKey('playingChordDiagramStrip')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('chordProgressBar')), findsOneWidget);
  });
}
