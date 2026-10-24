import 'package:chordsync/features/practice_timeline/application/practice_playback_status.dart';
import 'package:chordsync/features/practice_timeline/presentation/practice_transport_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late List<double> seeks;

  setUp(() => seeks = []);

  Widget bar(double position) => MaterialApp(
    home: Scaffold(
      body: PracticeTransportBar(
        status: PracticePlaybackStatus.playing,
        position: position,
        maximumPosition: 100,
        speed: 1,
        canGoPrevious: true,
        canGoNext: true,
        onPrevious: () {},
        onPlayPause: () {},
        onNext: () {},
        onSeek: seeks.add,
        onSpeedChanged: (_) {},
      ),
    ),
  );

  double handle(WidgetTester tester) =>
      tester.widget<Slider>(find.byType(Slider)).value;

  testWidgets('dragging seeks once, when the finger lifts', (tester) async {
    await tester.pumpWidget(bar(10));

    final gesture = await tester.startGesture(
      tester.getCenter(find.byType(Slider)),
    );
    await gesture.moveBy(const Offset(20, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(20, 0));
    await tester.pump();
    expect(seeks, isEmpty);

    await gesture.up();
    await tester.pump();
    expect(seeks, hasLength(1));
  });

  testWidgets('playback updates do not pull the handle while dragging', (
    tester,
  ) async {
    await tester.pumpWidget(bar(10));
    final gesture = await tester.startGesture(
      tester.getCenter(find.byType(Slider)),
    );
    await gesture.moveBy(const Offset(40, 0));
    await tester.pump();
    final dragged = handle(tester);

    await tester.pumpWidget(bar(11)); // the song moves on by itself
    await tester.pump();
    expect(handle(tester), dragged);

    await gesture.up();
    await tester.pump(const Duration(seconds: 1)); // no jump back either
    await tester.pump();
  });

  testWidgets('the handle follows playback again once the seek has landed', (
    tester,
  ) async {
    await tester.pumpWidget(bar(10));
    final gesture = await tester.startGesture(
      tester.getCenter(find.byType(Slider)),
    );
    await gesture.moveBy(const Offset(40, 0));
    await tester.pump();
    final target = handle(tester);
    await gesture.up();
    await tester.pump();

    await tester.pumpWidget(bar(target + 0.2)); // player reports the new spot
    await tester.pump();
    await tester.pumpWidget(bar(target + 5));
    await tester.pump();
    expect(handle(tester), closeTo(target + 5, 0.01));
  });
}
