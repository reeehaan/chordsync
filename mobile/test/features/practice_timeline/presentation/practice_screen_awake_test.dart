import 'package:chordsync/features/practice_timeline/application/screen_awake.dart';
import 'package:chordsync/features/practice_timeline/presentation/practice_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/fake_practice_audio_player.dart';

class _RecordingScreenAwake implements ScreenAwake {
  final calls = <bool>[];

  @override
  Future<void> setAwake(bool awake) async => calls.add(awake);
}

void main() {
  testWidgets('keeps the screen awake only while the song plays', (
    tester,
  ) async {
    final awake = _RecordingScreenAwake();
    await tester.pumpWidget(
      MaterialApp(
        home: PracticeScreen(
          audioPlayer: FakePracticeAudioPlayer(),
          screenAwake: awake,
        ),
      ),
    );
    for (var attempt = 0; attempt < 100; attempt++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find.byType(Slider).evaluate().isNotEmpty) break;
    }
    expect(find.byType(Slider), findsOneWidget);
    expect(awake.calls, isEmpty);

    // The lyric sweep animates while playing, so pump for a fixed time.
    Future<void> tap(String tooltip) async {
      await tester.tap(find.byTooltip(tooltip));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
    }

    await tap('Play');
    expect(awake.calls, [true]);

    await tap('Pause');
    expect(awake.calls, [true, false]);

    await tap('Play');
    await tester.pumpWidget(const SizedBox());
    expect(awake.calls, [true, false, true, false]);
  });
}
