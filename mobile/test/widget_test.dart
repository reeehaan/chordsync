import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'features/practice_timeline/fakes/fake_practice_audio_player.dart';

void main() {
  testWidgets('normal app entry opens on the song library', (tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Upload'), findsNothing);
    expect(find.text('ChordSync Practice'), findsNothing);

    // The Upload tab offers only uploading a file.
    await tester.tap(find.byKey(const ValueKey('bottomNav1')));
    await tester.pumpAndSettle();
    expect(find.text('Upload'), findsOneWidget);
    expect(find.text('Upload from files'), findsWidgets);
    expect(find.text('Shazam'), findsNothing);
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
