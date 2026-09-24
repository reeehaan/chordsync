import 'package:chordsync/features/practice_timeline/presentation/chord_diagram.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('known chord paints a six-string diagram', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: ChordDiagram(chord: 'C')),
      ),
    );
    expect(find.byKey(const ValueKey('chordDiagram')), findsOneWidget);
  });

  testWidgets('barre chords with no open shape render a diagram', (
    tester,
  ) async {
    for (final chord in ['F#', 'G#', 'A#', 'Bm', 'C#', 'D#m']) {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: ChordDiagram(chord: chord)),
        ),
      );
      expect(
        find.byKey(const ValueKey('chordDiagram')),
        findsOneWidget,
        reason: '$chord should render a barre voicing, not a fallback',
      );
      expect(find.byKey(const ValueKey('unknownChordFallback')), findsNothing);
    }
  });

  testWidgets('unknown chord and N never invent a fingering', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: ChordDiagram(chord: 'Cmaj7')),
      ),
    );
    expect(find.byKey(const ValueKey('unknownChordFallback')), findsOneWidget);
    expect(find.byKey(const ValueKey('chordDiagram')), findsNothing);

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: ChordDiagram(chord: 'N')),
      ),
    );
    expect(find.text('Rest / No chord'), findsOneWidget);
    expect(find.byKey(const ValueKey('chordDiagram')), findsNothing);
  });
}
