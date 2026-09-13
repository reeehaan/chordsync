import 'package:chordsync/features/practice_timeline/presentation/practice_beat_indicator.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> pumpIndicator(
    WidgetTester tester, {
    required int? beatNumber,
    int beatsPerBar = 4,
    bool isDownbeat = false,
  }) {
    return tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PracticeBeatIndicator(
            beatNumber: beatNumber,
            beatsPerBar: beatsPerBar,
            isDownbeat: isDownbeat,
          ),
        ),
      ),
    );
  }

  testWidgets('renders all markers with no active beat', (tester) async {
    await pumpIndicator(tester, beatNumber: null);

    for (var beat = 1; beat <= 4; beat++) {
      expect(find.byKey(ValueKey('beatMarker$beat')), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('activeBeatMarker')), findsNothing);
    expect(
      tester
          .getSemantics(find.byKey(const ValueKey('practiceBeatIndicator')))
          .label,
      'No active beat',
    );
  });

  testWidgets('highlights beat 1 with stronger downbeat emphasis', (
    tester,
  ) async {
    await pumpIndicator(tester, beatNumber: 1, isDownbeat: true);

    final active = find.byKey(const ValueKey('activeBeatMarker'));
    expect(
      find.descendant(
        of: active,
        matching: find.byKey(const ValueKey('beatMarker1')),
      ),
      findsOneWidget,
    );
    expect(tester.getSize(active), const Size.square(24));
    expect(
      tester
          .getSemantics(find.byKey(const ValueKey('practiceBeatIndicator')))
          .label,
      'Beat 1 of 4, downbeat',
    );
  });

  testWidgets('highlights another beat and supports dynamic meter', (
    tester,
  ) async {
    await pumpIndicator(tester, beatNumber: 2, beatsPerBar: 3);

    final active = find.byKey(const ValueKey('activeBeatMarker'));
    expect(
      find.descendant(
        of: active,
        matching: find.byKey(const ValueKey('beatMarker2')),
      ),
      findsOneWidget,
    );
    expect(tester.getSize(active), const Size.square(20));
    expect(find.byKey(const ValueKey('beatMarker3')), findsOneWidget);
    expect(find.byKey(const ValueKey('beatMarker4')), findsNothing);
    expect(
      tester
          .getSemantics(find.byKey(const ValueKey('practiceBeatIndicator')))
          .label,
      'Beat 2 of 3',
    );
  });
}
