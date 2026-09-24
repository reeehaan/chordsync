import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'features/practice_timeline/fakes/fake_practice_audio_player.dart';

void main() {
  testWidgets('normal app entry opens the audio import flow', (tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('ChordSync'), findsOneWidget);
    expect(find.text('Previously analyzed'), findsOneWidget);
    expect(find.text('0 saved'), findsOneWidget);
    expect(
      find.text('Your completed songs will appear here for quick practice.'),
      findsOneWidget,
    );
    expect(find.text('Choose audio file'), findsOneWidget);
    expect(find.text('Analyze Song'), findsOneWidget);
    expect(find.text('ChordSync Practice'), findsNothing);
  });

  testWidgets('explicit fixture entry still opens the practice screen', (
    tester,
  ) async {
    await tester.pumpWidget(MyApp(audioPlayer: FakePracticeAudioPlayer()));
    await tester.pumpAndSettle();

    expect(find.text('Practice sheet'), findsOneWidget);
    expect(find.byKey(const ValueKey('currentChordValue')), findsOneWidget);
    expect(find.byTooltip('Play'), findsOneWidget);
  });
}
