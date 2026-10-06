import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'features/practice_timeline/fakes/fake_practice_audio_player.dart';

void main() {
  testWidgets('normal app entry opens the audio import flow', (tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('Upload'), findsOneWidget);
    expect(find.text('Shazam'), findsOneWidget);
    expect(find.text('Files'), findsOneWidget);
    expect(find.text('Upload from local files'), findsOneWidget);
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
