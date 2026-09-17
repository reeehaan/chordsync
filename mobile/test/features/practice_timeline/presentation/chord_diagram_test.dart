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
