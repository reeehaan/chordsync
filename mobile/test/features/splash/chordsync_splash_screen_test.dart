import 'dart:ui' as ui;

import 'package:chordsync/design_system/chordsync_design_system.dart';
import 'package:chordsync/features/splash/chordsync_splash_screen.dart';
import 'package:chordsync/features/splash/splash_sound.dart';
import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _RecordingSound implements SplashSound {
  int loads = 0;
  int plays = 0;
  int disposes = 0;

  @override
  Future<void> load() async => loads++;

  @override
  Future<void> play() async => plays++;

  @override
  Future<void> dispose() async => disposes++;
}

void main() {
  Widget splash(
    VoidCallback onFinished, {
    SplashSound? sound,
    bool reduceMotion = false,
  }) => MaterialApp(
    home: Builder(
      builder: (context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
        child: ChordSyncSplashScreen(
          onFinished: onFinished,
          sound: sound ?? const NoSplashSound(),
        ),
      ),
    ),
  );

  testWidgets('shows only the icon: no name, no tagline', (tester) async {
    await tester.pumpWidget(splash(() {}));
    expect(find.byType(Text), findsNothing);
    expect(find.bySemanticsLabel('ChordSync'), findsOneWidget);
    await tester.pump(ChordSyncSplashScreen.duration);
  });

  testWidgets('the sound starts just before the first note, once', (
    tester,
  ) async {
    final sound = _RecordingSound();
    await tester.pumpWidget(splash(() {}, sound: sound));
    expect(sound.loads, 1); // ready early, so playing is instant

    const lead = ChordSyncSplashScreen.soundLeadMs;
    await tester.pump(
      Duration(
        milliseconds: (ChordSyncSplashScreen.pickStartMs - lead - 100).round(),
      ),
    );
    expect(sound.plays, 0);

    // The first note is picked at pickStartMs; the sound leads it a little.
    await tester.pump(const Duration(milliseconds: 200));
    expect(sound.plays, 1);

    await tester.pump(const Duration(milliseconds: 1000));
    expect(sound.plays, 1);
    await tester.pump(ChordSyncSplashScreen.duration);
  });

  testWidgets('hands over once, when the picking has played out', (
    tester,
  ) async {
    var finished = 0;
    await tester.pumpWidget(splash(() => finished++));

    await tester.pump(
      ChordSyncSplashScreen.duration - const Duration(milliseconds: 200),
    );
    expect(finished, 0);
    await tester.pump(const Duration(milliseconds: 300));
    expect(finished, 1);
  });

  testWidgets('with Reduce Motion: finished icon, no sound, then on', (
    tester,
  ) async {
    final sound = _RecordingSound();
    var finished = 0;
    await tester.pumpWidget(
      splash(() => finished++, sound: sound, reduceMotion: true),
    );

    expect(sound.loads, 0);
    expect(finished, 0);
    await tester.pump(ChordSyncSplashScreen.reducedMotionDuration);
    expect(finished, 1);
    expect(sound.plays, 0);
  });

  testWidgets('the sound is let go when the splash goes', (tester) async {
    final sound = _RecordingSound();
    await tester.pumpWidget(splash(() {}, sound: sound));
    await tester.pump(ChordSyncSplashScreen.duration);

    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    expect(sound.disposes, 1);
  });

  test('the tab is picked on five strings, as the icon draws them', () {
    const picks = ChordSyncSplashScreen.pickStrings;
    expect(picks.toSet(), {0, 1, 2, 3, 4});
    // 5th, 4th, 3rd, 2nd, 1st string, then back down the 2nd, 3rd and 4th.
    expect(picks, [4, 3, 2, 1, 0, 1, 2, 3]);
  });

  group('the drawing', () {
    Future<ui.Image> draw(double elapsedMs) async {
      final recorder = ui.PictureRecorder();
      ChordSyncMarkPainter(
        elapsedMs: elapsedMs,
      ).paint(Canvas(recorder), const Size(300, 300));
      return recorder.endRecording().toImage(300, 300);
    }

    Future<List<int>> pixels(double elapsedMs) async {
      final image = await draw(elapsedMs);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      return bytes!.buffer.asUint8List().toList();
    }

    testWidgets('builds up, then moves when notes are picked', (tester) async {
      await tester.runAsync(() async {
        final empty = await pixels(0);
        final drawn = await pixels(880); // shape and strings in, none picked
        final stillAgain = await pixels(895); // just before the first note
        final picked = await pixels(1050); // the first notes are ringing

        expect(drawn, isNot(empty));
        expect(stillAgain.length, drawn.length);
        expect(picked, isNot(drawn)); // the strings are moving
      });
    });

    test('a quiet string has settled by the end', () {
      final painter = ChordSyncMarkPainter(elapsedMs: 0);
      expect(painter.shouldRepaint(ChordSyncMarkPainter(elapsedMs: 1)), isTrue);
      expect(
        painter.shouldRepaint(ChordSyncMarkPainter(elapsedMs: 0)),
        isFalse,
      );
    });
  });

  testWidgets('the app opens on the splash, then the library', (tester) async {
    await tester.pumpWidget(
      const MyApp(showSplash: true, splashSound: NoSplashSound()),
    );
    expect(find.bySemanticsLabel('ChordSync'), findsOneWidget);
    expect(find.text('Home'), findsNothing);

    await tester.pump(ChordSyncSplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.bySemanticsLabel('ChordSync'), findsNothing);
    expect(find.text('Home'), findsOneWidget);
  });

  testWidgets('parchment sits behind the hand-over, so it cannot flash black', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MyApp(showSplash: true, splashSound: NoSplashSound()),
    );
    final behind = find.ancestor(
      of: find.byType(AnimatedSwitcher),
      matching: find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox && widget.color == ChordSyncColors.background,
      ),
    );
    expect(behind, findsWidgets);

    // And in the middle of the fade, the screen is still showing something.
    await tester.pump(ChordSyncSplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 70));
    expect(find.byType(AnimatedSwitcher), findsWidgets);
    await tester.pump(const Duration(milliseconds: 400));
  });
}
