import 'dart:io';

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/presentation/audio_file_selector.dart';
import 'package:chordsync/features/analysis/presentation/audio_import_controller.dart';
import 'package:chordsync/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('real user import flow reaches synchronized local playback', (
    tester,
  ) async {
    final setup = await tester.runAsync(() async {
      final directory = await Directory.systemTemp.createTemp(
        'chordsync-s5-t07-smoke-',
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
      final controller = AudioImportController(
        preparation: AnalysisPracticeCoordinator(
          client: client,
          polling: AnalysisJobPoller(
            client: client,
            pollingInterval: const Duration(milliseconds: 250),
          ),
        ),
      );
      return (
        directory: directory,
        audioFile: audioFile,
        controller: controller,
      );
    });
    expect(setup, isNotNull);
    final phases = <AudioImportPhase>[];
    final progressValues = <double>[];
    setup!.controller.addListener(() {
      phases.add(setup.controller.phase);
      final progress = setup.controller.uploadProgress;
      if (progress != null) progressValues.add(progress);
    });

    await tester.pumpWidget(
      MyApp(
        importController: setup.controller,
        fileSelector: _KnownAudioSelector(setup.audioFile),
      ),
    );
    expect(find.text('Choose audio file'), findsOneWidget);

    await tester.tap(find.text('Choose audio file'));
    await tester.pump();
    expect(find.text('synthetic_practice.wav'), findsOneWidget);
    expect(find.textContaining(setup.directory.path), findsNothing);

    await tester.ensureVisible(find.text('Analyze Song'));
    await tester.tap(find.text('Analyze Song'));
    await tester.pump();
    expect(find.text('Stop waiting'), findsOneWidget);
    for (var attempt = 0; attempt < 900; attempt++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(seconds: 1)),
      );
      await tester.pump();
      if (setup.controller.phase == AudioImportPhase.ready) break;
    }
    await tester.pump();
    expect(setup.controller.phase, AudioImportPhase.ready);
    expect(progressValues, isNotEmpty);
    expect(phases, contains(AudioImportPhase.queued));
    expect(phases, contains(AudioImportPhase.processing));
    expect(phases, contains(AudioImportPhase.preparing));
    expect(find.text('Start Practice'), findsOneWidget);

    await tester.ensureVisible(find.text('Start Practice'));
    await tester.tap(find.text('Start Practice'));
    for (var attempt = 0; attempt < 100; attempt++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find.byTooltip('Play').evaluate().isNotEmpty) break;
    }
    expect(find.text('ChordSync Practice'), findsOneWidget);
    expect(find.byKey(const ValueKey('currentChordValue')), findsOneWidget);

    await tester.ensureVisible(find.byTooltip('Play'));
    await tester.tap(find.byTooltip('Play'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 600)),
    );
    await tester.pump();
    expect(find.byTooltip('Pause'), findsOneWidget);
    await tester.tap(find.byTooltip('Pause'));
    await tester.pump();
    expect(find.byTooltip('Play'), findsOneWidget);

    final slider = tester.widget<Slider>(find.byType(Slider));
    slider.onChanged!(2);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 100)),
    );
    await tester.pump();
    expect(find.text('2.0 s'), findsOneWidget);

    await tester.ensureVisible(find.text('Set A'));
    await tester.tap(find.text('Set A'));
    final laterSlider = tester.widget<Slider>(find.byType(Slider));
    laterSlider.onChanged!(4);
    await tester.pump();
    await tester.tap(find.text('Set B'));
    await tester.pump();
    await tester.tap(find.text('Loop On'));
    await tester.pump();
    expect(find.text('Loop Off'), findsOneWidget);
    await tester.tap(find.text('Loop Off'));
    await tester.ensureVisible(find.byKey(const ValueKey('speedSelector')));
    await tester.tap(find.byKey(const ValueKey('speedSelector')));
    await tester.pump();
    await tester.tap(find.text('0.75x').last);
    await tester.pump();
    expect(find.text('0.75x'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('nextBarButton')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('previousBarButton')));
    await tester.pump();

    await tester.pumpWidget(const SizedBox());
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await setup.directory.delete(recursive: true);
    });
  }, timeout: const Timeout(Duration(minutes: 20)));
}

class _KnownAudioSelector implements AudioFileSelector {
  const _KnownAudioSelector(this.file);

  final File file;

  @override
  Future<File?> chooseAudio() async => file;
}
