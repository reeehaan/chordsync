import 'package:chordsync/main.dart';
import 'package:flutter_test/flutter_test.dart';

import 'features/practice_timeline/fakes/fake_practice_audio_player.dart';

void main() {
  testWidgets('opens the practice screen', (WidgetTester tester) async {
    await tester.pumpWidget(MyApp(audioPlayer: FakePracticeAudioPlayer()));
    await tester.pumpAndSettle();

    expect(find.text('ChordSync Practice'), findsOneWidget);
    expect(find.text('Current chord'), findsOneWidget);
    expect(find.byTooltip('Play'), findsOneWidget);
  });
}
