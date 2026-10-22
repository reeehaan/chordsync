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

void main() {
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
