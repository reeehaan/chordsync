import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/practice_timeline/application/practice_session_factory.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/presentation/practice_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/fake_practice_audio_player.dart';
import '../../../fixtures/long_shared_timeline.dart';

void main() {
  testWidgets(
    'long synthetic sheet scrolls to its final line above transport',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 640);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final directory = Directory.systemTemp.createTempSync(
        'chordsync-long-sheet-',
      );
      addTearDown(() => directory.deleteSync(recursive: true));
      final audioFile = File('${directory.path}/synthetic.wav')
        ..writeAsBytesSync([1, 2, 3]);
      final player = _LongAudioPlayer();
      final session = AnalyzedPracticeSession(
        title: 'Long synthetic practice',
        job: AnalysisJob(
          jobId: 'long-sheet',
          status: AnalysisJobStatus.completed,
          createdAt: DateTime.utc(2026),
          updatedAt: DateTime.utc(2026),
          error: null,
          resultAvailable: true,
        ),
        audioFile: audioFile,
        timeline: longSharedTimeline(),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: PracticeScreen(
            analyzedSession: session,
            sessionFactory: PracticeSessionFactory(
              audioPlayerFactory: (_) => player,
            ),
          ),
        ),
      );
      for (var attempt = 0; attempt < 100; attempt++) {
        await tester.pump(const Duration(milliseconds: 10));
        if (find.byType(Slider).evaluate().isNotEmpty) break;
      }
      expect(tester.takeException(), isNull);
      expect(find.byTooltip('Play'), findsOneWidget);
      expect(find.text('Current chord'), findsOneWidget);
      expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('currentChordValue')))
            .style
            ?.fontWeight,
        FontWeight.w800,
      );
      expect(find.text('line40'), findsOneWidget);
      final scrollable = find.byType(Scrollable).first;
      final scrollPosition = tester.state<ScrollableState>(scrollable).position;
      expect(scrollPosition.pixels, 0);
      await tester.drag(scrollable, const Offset(0, -3000));
      await tester.pump();
      expect(scrollPosition.pixels, greaterThan(0));
      await tester.ensureVisible(find.text('line40'));
      await tester.pump();
      expect(
        tester.getBottomLeft(find.text('line40')).dy,
        lessThan(
          tester.getTopLeft(find.byKey(const ValueKey('transportSection'))).dy,
        ),
      );
      expect(scrollPosition.pixels, greaterThan(0));
      expect(find.byTooltip('Play'), findsOneWidget);
      expect(_text(tester, 'persistentChordValue'), 'Current C');
      expect(_text(tester, 'persistentNextChordValue'), 'Next G');
      expect(tester.takeException(), isNull);

      final bottomBeforeSeek = scrollPosition.pixels;
      player.emit(const Duration(seconds: 157));
      await tester.pump();
      expect(_text(tester, 'currentChordValue'), 'G');
      expect(_text(tester, 'barValue'), '40');
      expect(_text(tester, 'persistentChordValue'), 'Current G');
      expect(_text(tester, 'persistentNextChordValue'), 'Next Am');
      expect(scrollPosition.pixels, bottomBeforeSeek);
      expect(tester.takeException(), isNull);

      scrollPosition.jumpTo(scrollPosition.maxScrollExtent);
      await tester.pump();
      expect(
        tester.getBottomLeft(find.text('Clear Loop')).dy,
        lessThan(
          tester.getTopLeft(find.byKey(const ValueKey('transportSection'))).dy,
        ),
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('renders and owns an analyzed local practice session', (
    tester,
  ) async {
    final directory = Directory.systemTemp.createTempSync(
      'chordsync-screen-session-',
    );
    addTearDown(() => directory.deleteSync(recursive: true));
    final audioFile = File('${directory.path}/selected.wav')
      ..writeAsBytesSync([1, 2, 3]);
    final player = FakePracticeAudioPlayer();
    File? playerFile;
    final session = AnalyzedPracticeSession(
      title: 'Selected local audio',
      job: AnalysisJob(
        jobId: 'screen-job',
        status: AnalysisJobStatus.completed,
        createdAt: DateTime.utc(2026),
        updatedAt: DateTime.utc(2026),
        error: null,
        resultAvailable: true,
      ),
      audioFile: audioFile,
      timeline: const SharedTimeline(
        schemaVersion: 1,
        bpm: 120,
        beatsPerBar: 4,
        beatSource: 'test',
        lyricSource: 'none',
        bars: [
          TimelineBar(
            barNumber: 1,
            startTime: 0,
            endTime: 4,
            beats: [
              TimelineEvent(
                time: 1,
                beatNumber: 1,
                isDownbeat: true,
                chord: 'N',
              ),
              TimelineEvent(
                time: 2,
                beatNumber: 2,
                isDownbeat: false,
                chord: 'C',
              ),
            ],
          ),
        ],
        lyrics: [],
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: PracticeScreen(
          analyzedSession: session,
          sessionFactory: PracticeSessionFactory(
            audioPlayerFactory: (file) {
              playerFile = file;
              return player;
            },
          ),
        ),
      ),
    );
    for (var attempt = 0; attempt < 100; attempt++) {
      await tester.pump(const Duration(milliseconds: 10));
      if (find.byType(Slider).evaluate().isNotEmpty) break;
    }
    expect(find.byType(Slider), findsOneWidget);

    expect(playerFile, same(audioFile));
    expect(find.text('Selected local audio'), findsOneWidget);
    expect(find.text('No lyrics detected'), findsOneWidget);
    expect(find.byKey(const ValueKey('noChordFallback')), findsOneWidget);
    expect(_text(tester, 'currentChordValue'), 'N');
    expect(find.byKey(const ValueKey('lyricValue')), findsNothing);

    tester.widget<Slider>(find.byType(Slider)).onChanged!(2);
    await tester.pump();

    expect(_text(tester, 'currentChordValue'), 'C');
    expect(_text(tester, 'beatValue'), '2 / 4');
    expect(_text(tester, 'positionValue'), '2.0 s');

    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(milliseconds: 10));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    expect(player.disposed, isTrue);
  });
}

class _LongAudioPlayer extends FakePracticeAudioPlayer {
  @override
  Duration? get duration => const Duration(seconds: 160);
}

String? _text(WidgetTester tester, String key) {
  return tester.widget<Text>(find.byKey(ValueKey(key))).data;
}
