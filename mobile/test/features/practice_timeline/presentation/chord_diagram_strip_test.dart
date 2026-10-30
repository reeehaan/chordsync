import 'package:chordsync/features/practice_timeline/data/playback_state.dart';
import 'package:chordsync/features/practice_timeline/presentation/chord_diagram_strip.dart';
import 'package:chordsync/features/practice_timeline/presentation/practice_stage_colors.dart';
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

Widget _step({
  required String? previous,
  required String current,
  required String? next,
  required List<String> progression,
  required double start,
}) => MaterialApp(
  home: Scaffold(
    body: ChordDiagramStrip(
      previousChord: previous,
      currentChord: current,
      nextChord: next,
      progression: progression,
      chordProgress: 0,
      chordStart: start,
    ),
  ),
);

void main() {
  testWidgets('the enlarge button sits above the chord cards, not on them', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _step(
        previous: 'Am',
        current: 'C',
        next: 'G',
        progression: const ['C', 'G', 'F', 'C'],
        start: 4,
      ),
    );
    await tester.pumpAndSettle();

    final button = tester.getRect(
      find.byKey(const ValueKey('expandDiagramsButton')),
    );
    for (final key in [
      'currentChordValue',
      'nextChordValue',
      'upcomingChordValue4',
    ]) {
      final name = tester.getRect(find.byKey(ValueKey(key)));
      expect(button.overlaps(name), isFalse, reason: key);
    }
  });

  testWidgets('the current chord and the next two are fully on screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _step(
        previous: 'Am',
        current: 'C',
        next: 'G',
        progression: const ['C', 'G', 'F', 'C'],
        start: 4,
      ),
    );
    await tester.pumpAndSettle();

    for (final key in [
      'currentChordValue',
      'nextChordValue',
      'upcomingChordValue4',
    ]) {
      final box = tester.getRect(find.byKey(ValueKey(key)));
      expect(box.left, greaterThanOrEqualTo(0), reason: key);
      expect(box.right, lessThanOrEqualTo(390), reason: key);
    }
  });

  testWidgets('the chord after next shows even when it repeats the current', (
    tester,
  ) async {
    await tester.pumpWidget(
      _step(
        previous: null,
        current: 'C',
        next: 'G',
        progression: const ['C', 'G', 'C', 'G'],
        start: 0,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('nextChordValue')), findsOneWidget);
    final after = tester.widget<Text>(
      find.byKey(const ValueKey('upcomingChordValue4')),
    );
    expect(after.data, 'C');
  });

  testWidgets('a chord turning current is orange at once, never grey', (
    tester,
  ) async {
    Widget step(String? previous, String current, String next, double start) =>
        MaterialApp(
          home: Scaffold(
            body: ChordDiagramStrip(
              previousChord: previous,
              currentChord: current,
              nextChord: next,
              progression: const ['G', 'D', 'C', 'Am'],
              chordProgress: 0,
              chordStart: start,
            ),
          ),
        );
    Color? nameColor(String key) =>
        tester.widget<Text>(find.byKey(ValueKey(key))).style?.color;

    await tester.pumpWidget(step('Em', 'G', 'D', 1));
    await tester.pumpAndSettle();
    expect(nameColor('nextChordValue'), PracticeStageColors.textSecondary);

    await tester.pumpWidget(step('G', 'D', 'C', 2));
    // Frame by frame through the glide, the name that became current has
    // always been orange: no grey in between.
    for (var frame = 0; frame < 12; frame++) {
      await tester.pump(const Duration(milliseconds: 30));
      expect(
        nameColor('currentChordValue'),
        PracticeStageColors.amberBright,
        reason: 'frame $frame',
      );
    }
    await tester.pumpAndSettle();
  });

  testWidgets('unplayed beat segments are clearly visible', (tester) async {
    await tester.pumpWidget(_beatStrip(4, 1.5));
    await tester.pumpAndSettle();

    final track = tester
        .widgetList<ColoredBox>(
          find.descendant(
            of: find.byKey(const ValueKey('beatSegment3')),
            matching: find.byType(ColoredBox),
          ),
        )
        .map((box) => box.color);
    expect(track, contains(PracticeStageColors.beatTrack));
    // Darker than the faint card border, so it shows on the peach card.
    expect(
      PracticeStageColors.beatTrack.computeLuminance(),
      lessThan(PracticeStageColors.border.computeLuminance() - 0.2),
    );
    expect(
      PracticeStageColors.beatTrack.computeLuminance(),
      greaterThan(PracticeStageColors.amberBright.computeLuminance()),
    );
  });

  testWidgets('moving to the next chord glides the cards across', (
    tester,
  ) async {
    Widget before() => _step(
      previous: 'Em',
      current: 'G',
      next: 'D',
      progression: const ['G', 'D', 'C', 'Am'],
      start: 1,
    );
    Widget after() => _step(
      previous: 'G',
      current: 'D',
      next: 'C',
      progression: const ['D', 'C', 'Am', 'Bm'],
      start: 2,
    );
    double currentX() =>
        tester.getCenter(find.byKey(const ValueKey('currentChordValue'))).dx;

    await tester.pumpWidget(before());
    await tester.pumpAndSettle();
    final beforeX = currentX();

    await tester.pumpWidget(after());
    await tester.pump();
    // The old previous card is still there, fading out, and the new current
    // card starts off to the right of where it ends up.
    expect(find.byKey(const ValueKey('departingChordValue')), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 100));
    final midX = currentX();

    await tester.pumpAndSettle();
    final settledX = currentX();
    expect(find.byKey(const ValueKey('departingChordValue')), findsNothing);
    expect(midX, greaterThan(settledX));
    // It lands where the previous current card was.
    expect(settledX, closeTo(beforeX, 1));
    expect(
      tester.widget<Text>(find.byKey(const ValueKey('currentChordValue'))).data,
      'D',
    );
  });

  testWidgets('a jump to a different chord does not glide', (tester) async {
    await tester.pumpWidget(
      _step(
        previous: 'Em',
        current: 'G',
        next: 'D',
        progression: const ['G', 'D', 'C', 'Am'],
        start: 1,
      ),
    );
    await tester.pumpAndSettle();
    // Seeking lands on a chord that is not the next one.
    await tester.pumpWidget(
      _step(
        previous: 'C',
        current: 'Am',
        next: 'Bm',
        progression: const ['Am', 'Bm', 'Gm', 'Em'],
        start: 9,
      ),
    );
    await tester.pump();
    expect(find.byKey(const ValueKey('departingChordValue')), findsNothing);
  });

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
