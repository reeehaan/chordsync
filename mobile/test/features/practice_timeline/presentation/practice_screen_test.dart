import 'package:chordsync/features/practice_timeline/presentation/practice_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/fake_practice_audio_player.dart';

void main() {
  Future<void> pumpScreen(
    WidgetTester tester, {
    FakePracticeAudioPlayer? audioPlayer,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PracticeScreen(
          audioPlayer: audioPlayer ?? FakePracticeAudioPlayer(),
        ),
      ),
    );
    for (var attempt = 0; attempt < 100; attempt++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find.byType(Slider).evaluate().isNotEmpty) return;
    }
    fail('Practice screen did not finish loading.');
  }

  void expectState({
    required String chord,
    required String nextChord,
    required String bar,
    required String beat,
    required String downbeat,
    required String previousLyric,
    required String lyric,
    required String nextLyric,
    required String position,
    required List<String> progression,
  }) {
    void expectValue(String key, String value) {
      final text = find.byKey(ValueKey(key)).evaluate().single.widget as Text;
      expect(text.data, value);
    }

    expect(find.text('Bar'), findsNothing);
    expect(find.text('Beat'), findsNothing);
    expect(find.text('Downbeat'), findsNothing);
    expectValue('currentChordValue', chord);
    expectValue('nextChordValue', nextChord);
    expectValue('positionValue', position);
  }

  Future<void> setPosition(WidgetTester tester, double seconds) async {
    final slider = tester.widget<Slider>(find.byType(Slider));
    slider.onChanged!(seconds);
    await tester.pumpAndSettle();
  }

  Future<void> tapControl(WidgetTester tester, String tooltip) async {
    final control = find.byTooltip(tooltip);
    await tester.ensureVisible(control);
    await tester.tap(control);
    await tester.pumpAndSettle();
  }

  Future<void> tapTextButton(WidgetTester tester, String label) async {
    final button = find.text(label);
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();
  }

  Future<void> selectSpeed(
    WidgetTester tester,
    double speed,
    String label,
  ) async {
    final selector = find.byKey(const ValueKey('speedSelector'));
    await tester.ensureVisible(selector);
    await tester.tap(selector);
    await tester.pumpAndSettle();
    await tester.tap(find.text(label).last);
    await tester.pumpAndSettle();

    final dropdown = tester.widget<DropdownButton<double>>(selector);
    expect(dropdown.value, speed);
  }

  void expectBarNavigation(
    WidgetTester tester, {
    required bool previousEnabled,
    required bool nextEnabled,
  }) {
    final previous = tester.widget<IconButton>(
      find.byKey(const ValueKey('previousBarButton')),
    );
    final next = tester.widget<IconButton>(
      find.byKey(const ValueKey('nextBarButton')),
    );
    expect(previous.onPressed != null, previousEnabled);
    expect(next.onPressed != null, nextEnabled);
  }

  testWidgets(
    'renders synthetic playback states and supports backward scrubbing',
    (tester) async {
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final player = FakePracticeAudioPlayer();
      await pumpScreen(tester, audioPlayer: player);

      expect(find.byKey(const ValueKey('chordFocus')), findsOneWidget);
      expect(find.text('Practice sheet'), findsOneWidget);
      expect(find.byKey(const ValueKey('noChordFallback')), findsOneWidget);
      expect(find.byKey(const ValueKey('lyricsSection')), findsOneWidget);
      expect(find.byKey(const ValueKey('rhythmSection')), findsNothing);
      expect(find.byKey(const ValueKey('progressionSection')), findsNothing);
      expect(find.byKey(const ValueKey('transportSection')), findsOneWidget);
      expect(
        find.byKey(const ValueKey('practiceToolsSection')),
        findsOneWidget,
      );
      final currentChord = tester.widget<Text>(
        find.byKey(const ValueKey('currentChordValue')),
      );
      final nextChord = tester.widget<Text>(
        find.byKey(const ValueKey('nextChordValue')),
      );
      expect(
        currentChord.style!.fontSize!,
        greaterThan(nextChord.style!.fontSize!),
      );
      expect(currentChord.style?.fontWeight, FontWeight.w800);

      expectState(
        chord: 'N',
        nextChord: 'C',
        bar: '—',
        beat: '— / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: '—',
        nextLyric: 'Morning',
        position: '0.0 s',
        progression: ['C', 'G', 'Am', 'F'],
      );
      expect(find.text('Paused'), findsOneWidget);
      expect(find.byTooltip('Play'), findsOneWidget);
      expect(find.byTooltip('Previous bar'), findsOneWidget);
      expect(find.byTooltip('Next bar'), findsOneWidget);
      expectBarNavigation(tester, previousEnabled: false, nextEnabled: true);
      // The speed control is a compact circular button showing the rate
      // itself, so there is no separate "Speed" caption.
      expect(find.text('Speed'), findsNothing);
      expect(find.text('1.0x'), findsOneWidget);
      expect(
        tester
            .widget<DropdownButton<double>>(
              find.byKey(const ValueKey('speedSelector')),
            )
            .value,
        1.0,
      );

      await tapControl(tester, 'Next bar');
      expectState(
        chord: 'C',
        nextChord: 'G',
        bar: '1',
        beat: '1 / 4',
        downbeat: 'Yes',
        previousLyric: '—',
        lyric: '—',
        nextLyric: 'Morning',
        position: '1.0 s',
        progression: ['C', 'G', 'Am', 'F'],
      );
      expectBarNavigation(tester, previousEnabled: false, nextEnabled: true);

      await tapControl(tester, 'Next bar');
      expectState(
        chord: 'Dm',
        nextChord: 'G',
        bar: '2',
        beat: '1 / 4',
        downbeat: 'Yes',
        previousLyric: 'across',
        lyric: '—',
        nextLyric: 'the',
        position: '5.0 s',
        progression: ['Dm', 'G', 'C'],
      );
      expectBarNavigation(tester, previousEnabled: true, nextEnabled: false);

      await tapControl(tester, 'Previous bar');
      expectState(
        chord: 'C',
        nextChord: 'G',
        bar: '1',
        beat: '1 / 4',
        downbeat: 'Yes',
        previousLyric: '—',
        lyric: '—',
        nextLyric: 'Morning',
        position: '1.0 s',
        progression: ['C', 'G', 'Am', 'F'],
      );

      await setPosition(tester, 2);
      // Previous, current, and next chords remain visible in the fixed header.
      expect(find.byKey(const ValueKey('chordDiagram')), findsNWidgets(4));
      // Each strip card animates between its raised and resting appearance.
      expect(find.byType(AnimatedContainer), findsWidgets);
      expect(
        (find
                    .byKey(const ValueKey('previousChordValue'))
                    .evaluate()
                    .single
                    .widget
                as Text)
            .data,
        'C',
      );
      final headerTop = tester.getTopLeft(
        find.byKey(const ValueKey('fixedChordHeader')),
      );
      final transportTop = tester.getTopLeft(
        find.byKey(const ValueKey('transportSection')),
      );
      await tapControl(tester, 'Play');
      await tester.drag(
        find.byKey(const ValueKey('lyricScrollView')),
        const Offset(0, -100),
      );
      await tester.pumpAndSettle();
      expect(player.isPlaying, isTrue);
      expect(
        tester.getTopLeft(find.byKey(const ValueKey('fixedChordHeader'))),
        headerTop,
      );
      expect(
        tester.getTopLeft(find.byKey(const ValueKey('transportSection'))),
        transportTop,
      );
      expect(find.byKey(const ValueKey('followLyricsButton')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('followLyricsButton')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('followLyricsButton')), findsNothing);
      await tapControl(tester, 'Pause');
      final progressFinder = find.descendant(
        of: find.byKey(const ValueKey('chordProgressBar')),
        matching: find.byType(LinearProgressIndicator),
      );
      final progressAnimation = tester.widget<TweenAnimationBuilder<double>>(
        find.descendant(
          of: find.byKey(const ValueKey('chordProgressBar')),
          matching: find.byType(TweenAnimationBuilder<double>),
        ),
      );
      expect(progressAnimation.duration, const Duration(milliseconds: 180));
      expect(tester.widget<LinearProgressIndicator>(progressFinder).value, 0);
      final activeSheetWord = tester.widget<AnimatedDefaultTextStyle>(
        find.byKey(const ValueKey('sheetWordStyle1.5')),
      );
      expect(activeSheetWord.style.fontWeight, FontWeight.w800);
      await setPosition(tester, 2.5);
      expect(
        tester.widget<LinearProgressIndicator>(progressFinder).value,
        closeTo(0.5, 0.001),
      );
      final pastSheetWord = tester.widget<AnimatedDefaultTextStyle>(
        find.byKey(const ValueKey('sheetWordStyle1.5')),
      );
      expect(activeSheetWord.style.color, isNot(pastSheetWord.style.color));
      await setPosition(tester, 3);
      expect(tester.widget<LinearProgressIndicator>(progressFinder).value, 0);
      await setPosition(tester, 2);
      expectState(
        chord: 'G',
        nextChord: 'Am',
        bar: '1',
        beat: '2 / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: 'Morning',
        nextLyric: 'light',
        position: '2.0 s',
        progression: ['G', 'Am', 'F', 'Dm'],
      );

      await selectSpeed(tester, 0.5, '0.5x');
      expect(player.speedCalls.last, 0.5);
      expectState(
        chord: 'G',
        nextChord: 'Am',
        bar: '1',
        beat: '2 / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: 'Morning',
        nextLyric: 'light',
        position: '2.0 s',
        progression: ['G', 'Am', 'F', 'Dm'],
      );

      await selectSpeed(tester, 1.5, '1.5x');
      expect(player.speedCalls.last, 1.5);
      expectState(
        chord: 'G',
        nextChord: 'Am',
        bar: '1',
        beat: '2 / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: 'Morning',
        nextLyric: 'light',
        position: '2.0 s',
        progression: ['G', 'Am', 'F', 'Dm'],
      );

      await setPosition(tester, 3.5);
      expectState(
        chord: 'Am',
        nextChord: 'F',
        bar: '1',
        beat: '3 / 4',
        downbeat: 'No',
        previousLyric: 'light',
        lyric: 'moves',
        nextLyric: 'across',
        position: '3.5 s',
        progression: ['Am', 'F', 'Dm', 'G'],
      );

      await setPosition(tester, 4);
      expectState(
        chord: 'F',
        nextChord: 'Dm',
        bar: '1',
        beat: '4 / 4',
        downbeat: 'No',
        previousLyric: 'across',
        lyric: '—',
        nextLyric: 'the',
        position: '4.0 s',
        progression: ['F', 'Dm', 'G', 'C'],
      );

      await setPosition(tester, 6);
      expectState(
        chord: 'G',
        nextChord: 'C',
        bar: '2',
        beat: '2 / 4',
        downbeat: 'No',
        previousLyric: 'the',
        lyric: 'open',
        nextLyric: 'road',
        position: '6.0 s',
        progression: ['G', 'C'],
      );

      await setPosition(tester, 2);
      expectState(
        chord: 'G',
        nextChord: 'Am',
        bar: '1',
        beat: '2 / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: 'Morning',
        nextLyric: 'light',
        position: '2.0 s',
        progression: ['G', 'Am', 'F', 'Dm'],
      );

      String loopRange() {
        final text =
            find
                    .byKey(const ValueKey('loopRangeValue'))
                    .evaluate()
                    .single
                    .widget
                as Text;
        return text.data!;
      }

      expect(loopRange(), 'Not set');
      await tapTextButton(tester, 'Set A');
      expect(loopRange(), 'A: 2.0 s | B: —');
      await tapTextButton(tester, 'Set B');
      expect(loopRange(), 'A: 2.0 s | B: —');

      await setPosition(tester, 6);
      await tapTextButton(tester, 'Set B');
      expect(loopRange(), '2.0 s → 6.0 s');
      await selectSpeed(tester, 0.5, '0.5x');
      expect(loopRange(), '2.0 s → 6.0 s');
      await tapTextButton(tester, 'Loop On');
      expect(find.text('Loop Off'), findsOneWidget);

      await tapControl(tester, 'Previous bar');
      expect(loopRange(), '2.0 s → 6.0 s');
      expect(player.speed, 0.5);
      await tapControl(tester, 'Previous bar');
      expectState(
        chord: 'C',
        nextChord: 'G',
        bar: '1',
        beat: '1 / 4',
        downbeat: 'Yes',
        previousLyric: '—',
        lyric: '—',
        nextLyric: 'Morning',
        position: '1.0 s',
        progression: ['C', 'G', 'Am', 'F'],
      );
      expect(loopRange(), '2.0 s → 6.0 s');
      await tapControl(tester, 'Next bar');
      expect(loopRange(), '2.0 s → 6.0 s');
      expect(player.speed, 0.5);

      await setPosition(tester, 6);
      await tapControl(tester, 'Play');

      player.emit(const Duration(seconds: 6));
      await tester.pumpAndSettle();
      expect(player.seekCalls.last, const Duration(seconds: 2));
      expect(player.isPlaying, isTrue);
      expectState(
        chord: 'G',
        nextChord: 'Am',
        bar: '1',
        beat: '2 / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: 'Morning',
        nextLyric: 'light',
        position: '2.0 s',
        progression: ['G', 'Am', 'F', 'Dm'],
      );

      await tapTextButton(tester, 'Loop Off');
      expect(find.text('Loop On'), findsOneWidget);
      await tapControl(tester, 'Pause');

      await tapControl(tester, 'Play');
      expect(player.isPlaying, isTrue);
      expect(find.text('Playing'), findsOneWidget);
      expect(find.byTooltip('Pause'), findsOneWidget);

      await tapControl(tester, 'Pause');
      expect(player.isPlaying, isFalse);
      expect(find.text('Paused'), findsOneWidget);

      player.complete();
      await tester.pumpAndSettle();
      expect(find.text('Completed'), findsOneWidget);
      expect(find.byTooltip('Replay'), findsOneWidget);
      expectBarNavigation(tester, previousEnabled: true, nextEnabled: false);
      expectState(
        chord: 'C',
        nextChord: '—',
        bar: '2',
        beat: '4 / 4',
        downbeat: 'No',
        previousLyric: 'glows',
        lyric: '—',
        nextLyric: '—',
        position: '9.0 s',
        progression: ['C'],
      );

      await tapControl(tester, 'Replay');
      expect(find.text('Playing'), findsOneWidget);
      expect(player.speed, 0.5);
      expectBarNavigation(tester, previousEnabled: false, nextEnabled: true);
      expectState(
        chord: 'N',
        nextChord: 'C',
        bar: '—',
        beat: '— / 4',
        downbeat: 'No',
        previousLyric: '—',
        lyric: '—',
        nextLyric: 'Morning',
        position: '0.0 s',
        progression: ['C', 'G', 'Am', 'F'],
      );

      for (final size in const [
        Size(320, 640),
        Size(390, 844),
        Size(430, 932),
        Size(1024, 768),
      ]) {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = size;
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.byKey(const ValueKey('fixedChordHeader')), findsOneWidget);
        expect(find.byKey(const ValueKey('lyricScrollView')), findsOneWidget);
        expect(find.byKey(const ValueKey('transportSection')), findsOneWidget);
        expect(find.byKey(const ValueKey('speedSelector')), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    },
  );
}
