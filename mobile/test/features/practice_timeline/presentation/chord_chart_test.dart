import 'package:chordsync/design_system/chordsync_design_system.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/presentation/chord_chart.dart';
import 'package:chordsync/features/practice_timeline/presentation/song_sheet_lyrics.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

TimelineBar _bar(int number, double start, List<String> chords) => TimelineBar(
  barNumber: number,
  startTime: start,
  endTime: start + 2,
  beats: [
    for (var i = 0; i < chords.length; i++)
      TimelineEvent(
        time: start + i * (2 / chords.length),
        beatNumber: i + 1,
        isDownbeat: i == 0,
        chord: chords[i],
      ),
  ],
);

SharedTimeline _timeline(int bars) {
  const sequence = ['C', 'G', 'Am', 'F'];
  return SharedTimeline(
    schemaVersion: 1,
    bpm: 120,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'none',
    bars: [
      for (var i = 0; i < bars; i++)
        _bar(i + 1, i * 2.0, [sequence[i % 4], sequence[i % 4]]),
    ],
    lyrics: const [],
  );
}

Future<void> _pump(WidgetTester tester, SharedTimeline timeline, double time) {
  return tester.pumpWidget(
    MaterialApp(
      theme: ChordSyncTheme.light(),
      home: Scaffold(
        body: SizedBox(
          width: 390,
          height: 420,
          child: SongSheetLyrics(timeline: timeline, playbackTime: time),
        ),
      ),
    ),
  );
}

Color _fill(WidgetTester tester, int bar) {
  final container = tester.widget<Container>(
    find
        .descendant(
          of: find.byKey(ValueKey('chartBar$bar')),
          matching: find.byType(Container),
        )
        .first,
  );
  return (container.decoration! as BoxDecoration).color!;
}

void main() {
  test('a bar lists its chords in order, skipping gaps and repeats', () {
    final bar = _bar(1, 0, ['C', 'C', 'N', 'G']);

    expect(ChordChart.chordsOf(bar), ['C', 'G']);
    expect(ChordChart.chordsOf(_bar(2, 2, ['N', 'N'])), isEmpty);
  });

  test('the current bar is the last one that has started', () {
    final bars = _timeline(5).bars;

    expect(ChordChart.currentBar(bars, -1), 0);
    expect(ChordChart.currentBar(bars, 0), 0);
    expect(ChordChart.currentBar(bars, 3.9), 1);
    expect(ChordChart.currentBar(bars, 4.0), 2);
    expect(ChordChart.currentBar(bars, 99), 4);
  });

  testWidgets('a song without lyrics shows its chords bar by bar', (
    tester,
  ) async {
    await _pump(tester, _timeline(8), 0.5);

    expect(find.text('No lyrics detected'), findsOneWidget);
    expect(find.byKey(const ValueKey('chordChart')), findsOneWidget);
    expect(find.byKey(const ValueKey('chartBar0')), findsOneWidget);
    expect(find.text('C'), findsWidgets); // a repeated chord shows once
    expect(find.text('G'), findsWidgets);
    expect(find.text('C  C'), findsNothing);
  });

  testWidgets('the bar being played is highlighted', (tester) async {
    await _pump(tester, _timeline(8), 2.5); // bar 2

    expect(_fill(tester, 1), ChordSyncColors.currentChord);
    expect(_fill(tester, 0), ChordSyncColors.inactiveChord);
    expect(_fill(tester, 2), ChordSyncColors.inactiveChord);
  });

  testWidgets('the chart follows the song down the page', (tester) async {
    final timeline = _timeline(60);
    await _pump(tester, timeline, 0.5);
    final list = tester.widget<ListView>(
      find.byKey(const ValueKey('chordChart')),
    );
    expect(list.controller!.offset, 0);

    await _pump(tester, timeline, 100); // bar 51
    await tester.pumpAndSettle();

    expect(list.controller!.offset, greaterThan(0));
  });

  testWidgets('scrolling by hand pauses following until Follow is tapped', (
    tester,
  ) async {
    final timeline = _timeline(60);
    await _pump(tester, timeline, 0.5);

    await tester.drag(
      find.byKey(const ValueKey('chordChart')),
      const Offset(0, -150),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('followChordsButton')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('followChordsButton')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('followChordsButton')), findsNothing);
  });
}
