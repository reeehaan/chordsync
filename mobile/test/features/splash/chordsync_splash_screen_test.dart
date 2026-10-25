import 'package:chordsync/features/splash/chordsync_splash_screen.dart';
import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget splash(VoidCallback onFinished, {bool reduceMotion = false}) =>
      MaterialApp(
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(disableAnimations: reduceMotion),
            child: ChordSyncSplashScreen(onFinished: onFinished),
          ),
        ),
      );

  testWidgets('plays the intro, then hands over once', (tester) async {
    var finished = 0;
    await tester.pumpWidget(splash(() => finished++));

    // The icon is on its way in and the name is not shown yet.
    expect(find.text('ChordSync'), findsOneWidget);
    final nameOpacity = tester.widget<FadeTransition>(
      find
          .ancestor(
            of: find.text('ChordSync'),
            matching: find.byType(FadeTransition),
          )
          .first,
    );
    expect(nameOpacity.opacity.value, 0);

    await tester.pump(const Duration(milliseconds: 1800));
    expect(finished, 0);
    expect(nameOpacity.opacity.value, 1);
    expect(find.text('Find your rhythm.'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 500));
    expect(finished, 1);
  });

  testWidgets('with Reduce Motion the finished frame shows, then moves on', (
    tester,
  ) async {
    var finished = 0;
    await tester.pumpWidget(splash(() => finished++, reduceMotion: true));

    expect(find.text('Find your rhythm.'), findsOneWidget);
    expect(finished, 0);

    await tester.pump(ChordSyncSplashScreen.reducedMotionDuration);
    expect(finished, 1);
  });

  testWidgets('the app opens on the splash, then the library', (tester) async {
    await tester.pumpWidget(const MyApp(showSplash: true));
    expect(find.text('ChordSync'), findsOneWidget);

    await tester.pump(ChordSyncSplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('ChordSync'), findsNothing);
    expect(find.text('Your songs'), findsOneWidget);
  });
}
