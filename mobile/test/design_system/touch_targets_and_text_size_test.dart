import 'package:chordsync/features/practice_timeline/presentation/chord_diagram_strip.dart';
import 'package:chordsync/features/practice_timeline/presentation/follow_button.dart';
import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../features/practice_timeline/fakes/fake_practice_audio_player.dart';

void main() {
  testWidgets('the Follow button is at least 44pt tall', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(child: FollowButton(onPressed: () {})),
        ),
      ),
    );
    expect(
      tester.getSize(find.byType(FilledButton)).height,
      greaterThanOrEqualTo(44),
    );
  });

  testWidgets('the enlarge-shapes button has a 44pt touch target', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ChordDiagramStrip(
            previousChord: null,
            currentChord: 'Em',
            nextChord: 'G',
            progression: ['Em', 'G', 'D'],
            chordProgress: 0,
            chordStart: 0,
          ),
        ),
      ),
    );
    await tester.pump();

    final size = tester.getSize(
      find.byKey(const ValueKey('expandDiagramsButton')),
    );
    expect(size.width, greaterThanOrEqualTo(44));
    expect(size.height, greaterThanOrEqualTo(44));
  });

  testWidgets('large text sizes are followed, up to what the layouts hold', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.pumpWidget(MyApp(audioPlayer: FakePracticeAudioPlayer()));
    await tester.pump(const Duration(milliseconds: 200));

    final context = tester.element(find.byType(Scaffold).first);
    final scaler = MediaQuery.textScalerOf(context);
    // 2.0 was asked for; 1.3 is what the fixed-height rows can hold.
    expect(scaler.scale(10), closeTo(13, 0.01));
    expect(tester.takeException(), isNull, reason: 'no overflow at large text');
  });

  testWidgets('normal and smaller text sizes are untouched', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.15;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.pumpWidget(MyApp(audioPlayer: FakePracticeAudioPlayer()));
    await tester.pump(const Duration(milliseconds: 200));

    expect(
      MediaQuery.textScalerOf(
        tester.element(find.byType(Scaffold).first),
      ).scale(10),
      closeTo(11.5, 0.01),
    );
  });
}
