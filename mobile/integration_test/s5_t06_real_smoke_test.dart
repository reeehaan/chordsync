import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/practice_timeline/application/practice_playback_status.dart';
import 'package:chordsync/features/practice_timeline/application/practice_session_factory.dart';
import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('real backend result drives local native practice playback', (
    tester,
  ) async {
    final result = await tester.runAsync(() async {
      final directory = await Directory.systemTemp.createTemp(
        'chordsync-s5-t06-smoke-',
      );
      final bytes = await rootBundle.load(
        'assets/practice_audio/synthetic_practice.wav',
      );
      final audioFile = File('${directory.path}/synthetic_practice.wav');
      await audioFile.writeAsBytes(bytes.buffer.asUint8List(), flush: true);

      final client = DioAnalysisApiClient(
        baseUrl: const String.fromEnvironment(
          'CHORDSYNC_API_BASE_URL',
          defaultValue: 'http://127.0.0.1:8765',
        ),
      );
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: AnalysisJobPoller(
          client: client,
          pollingInterval: const Duration(milliseconds: 250),
        ),
      );
      final session = await coordinator.prepare(
        title: 'S5-T06 publication-safe smoke',
        audioFile: audioFile,
      );
      expect(session.audioFile, same(audioFile));
      expect(session.timeline.schemaVersion, 1);
      expect(session.timeline.bars, isNotEmpty);

      final practice = await PracticeSessionFactory().create(session);
      final duration = practice.audioPlayer.duration;
      expect(duration, isNotNull);
      expect(duration, greaterThan(Duration.zero));

      unawaited(practice.synchronizer.play());
      await Future<void>.delayed(const Duration(milliseconds: 600));
      expect(practice.synchronizer.status, PracticePlaybackStatus.playing);
      expect(practice.playbackController.position, greaterThan(Duration.zero));

      await practice.synchronizer.pause();
      final pausedPosition = practice.playbackController.position;
      expect(practice.synchronizer.status, PracticePlaybackStatus.paused);

      await practice.synchronizer.seek(const Duration(seconds: 2));
      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(practice.playbackController.position, const Duration(seconds: 2));
      expect(practice.playbackController.state.chord, isNotEmpty);
      expect(practice.playbackController.state.currentBarNumber, isNotNull);
      expect(practice.playbackController.state.beatNumber, isNotNull);
      expect(pausedPosition, isNot(const Duration(seconds: 2)));

      await practice.synchronizer.seek(duration!);
      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(practice.synchronizer.status, PracticePlaybackStatus.completed);
      await practice.dispose();

      return (session: session, directory: directory);
    });
    expect(result, isNotNull);

    await tester.pumpWidget(MyApp(analyzedSession: result!.session));
    for (var attempt = 0; attempt < 100; attempt++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find.byKey(const ValueKey('chordFocus')).evaluate().isNotEmpty) {
        break;
      }
    }
    expect(find.byKey(const ValueKey('chordFocus')), findsOneWidget);
    expect(find.byKey(const ValueKey('beatValue')), findsOneWidget);
    expect(find.byKey(const ValueKey('transportSection')), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await result.directory.delete(recursive: true);
    });
  }, timeout: const Timeout(Duration(minutes: 15)));
}
