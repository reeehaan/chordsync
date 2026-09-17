import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/presentation/audio_file_selector.dart';
import 'package:chordsync/features/analysis/presentation/audio_import_controller.dart';
import 'package:chordsync/features/analysis/presentation/audio_import_screen.dart';
import 'package:chordsync/features/practice_timeline/application/practice_session_factory.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../practice_timeline/fakes/fake_practice_audio_player.dart';

void main() {
  late Directory directory;
  late File audio;
  late _FakePreparation preparation;
  late AudioImportController controller;
  late _FakeFileSelector selector;
  late FakePracticeAudioPlayer practicePlayer;

  setUp(() {
    directory = Directory.systemTemp.createTempSync('chordsync-screen-test-');
    audio = File('${directory.path}/safe_song.wav')
      ..writeAsBytesSync(List.filled(2048, 1));
    preparation = _FakePreparation();
    controller = AudioImportController(preparation: preparation);
    selector = _FakeFileSelector(audio);
    practicePlayer = FakePracticeAudioPlayer();
  });

  tearDown(() {
    if (!controller.isDisposed) controller.dispose();
    directory.deleteSync(recursive: true);
  });

  Future<void> pumpScreen(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: AudioImportScreen(
          controller: controller,
          fileSelector: selector,
          practiceSessionFactory: PracticeSessionFactory(
            audioPlayerFactory: (_) => practicePlayer,
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('selects audio and presents upload through ready states', (
    tester,
  ) async {
    await pumpScreen(tester);

    expect(find.text('ChordSync'), findsOneWidget);
    expect(find.textContaining('WAV · MP3 · M4A'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Analyze Song'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, 'Analyze Song'),
          )
          .onPressed,
      isNull,
    );
    final disabled = tester.getSemantics(
      find.byKey(const ValueKey('analyzeButton')),
    );
    expect(disabled.flagsCollection.isEnabled, ui.Tristate.isFalse);
    await tester.tap(find.byKey(const ValueKey('analyzeButton')));
    await tester.pump();
    expect(preparation.calls, 0);

    await tester.tap(find.text('Choose audio file'));
    await tester.pump();
    expect(find.text('safe_song.wav'), findsOneWidget);
    expect(find.textContaining('2.0 KB'), findsOneWidget);
    expect(find.textContaining(directory.path), findsNothing);

    final analyze = find.widgetWithText(FilledButton, 'Analyze Song');
    await tester.ensureVisible(analyze);
    await tester.tap(analyze);
    await tester.tap(analyze);
    await tester.pump();
    expect(preparation.calls, 1);
    expect(find.text('Uploading your song…'), findsOneWidget);
    expect(find.text('Stop waiting'), findsOneWidget);

    preparation.emitProgress(1, 2);
    await tester.pump();
    expect(find.text('Uploading your song… 50%'), findsOneWidget);

    preparation.emitJob(AnalysisJobStatus.queued);
    await tester.pump();
    expect(find.text('Waiting to analyze…'), findsOneWidget);
    preparation.emitJob(AnalysisJobStatus.processing);
    await tester.pump();
    expect(find.text('Analyzing your song…'), findsOneWidget);
    preparation.emitJob(AnalysisJobStatus.completed);
    await tester.pump();
    expect(find.text('Preparing your practice sheet…'), findsOneWidget);

    preparation.complete(_session(audio));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    expect(find.text('Ready to practice'), findsOneWidget);
    expect(find.text('Start Practice'), findsOneWidget);

    await tester.ensureVisible(find.text('Start Practice'));
    await tester.tap(find.text('Start Practice'));
    await tester.pumpAndSettle();
    expect(find.text('ChordSync Practice'), findsOneWidget);
    expect(find.byKey(const ValueKey('currentChordValue')), findsOneWidget);

    Navigator.of(tester.element(find.text('ChordSync Practice'))).pop();
    await tester.pumpAndSettle();
    expect(find.text('Ready to practice'), findsOneWidget);
    expect(find.text('safe_song.wav'), findsOneWidget);
  });

  testWidgets('shows safe errors, supports retry, and cancels locally', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tester.tap(find.text('Choose audio file'));
    await tester.pump();
    preparation.nextError = const AnalysisTransportException(
      'private host detail',
    );
    await tester.runAsync(controller.analyze);
    await tester.pump();
    expect(
      find.text("ChordSync can't reach the analysis service."),
      findsOneWidget,
    );
    expect(find.textContaining('private'), findsNothing);
    expect(find.text('Retry Analysis'), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);

    await tester.ensureVisible(find.text('Retry Analysis'));
    await tester.tap(find.text('Retry Analysis'));
    await tester.pump();
    expect(preparation.calls, 2);
    await tester.ensureVisible(find.text('Stop waiting'));
    await tester.tap(find.text('Stop waiting'));
    await tester.pump();
    expect(preparation.cancellations.last.isCancelled, isTrue);
    expect(find.text('Stopped waiting. You can try again.'), findsOneWidget);
    expect(find.text('Analyze Song'), findsOneWidget);
    expect(find.text('safe_song.wav'), findsOneWidget);
  });

  testWidgets('remains usable without overflow at supported sizes', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.devicePixelRatio = 1;

    for (final size in const [
      Size(320, 640),
      Size(390, 844),
      Size(430, 932),
      Size(1024, 768),
    ]) {
      tester.view.physicalSize = size;
      await pumpScreen(tester);
      expect(tester.takeException(), isNull);
      expect(find.text('Choose audio file'), findsOneWidget);
      expect(find.text('Analyze Song'), findsOneWidget);
    }
  });

  testWidgets(
    'short viewport keeps focused title reachable above keyboard inset',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 640);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewInsets);
      await pumpScreen(tester);
      await tester.tap(find.text('Choose audio file'));
      await tester.pump();
      final title = find.byType(TextFormField);
      tester.view.viewInsets = const FakeViewPadding(bottom: 300);
      await tester.pump();
      await tester.ensureVisible(title);
      await tester.tap(title);
      await tester.pumpAndSettle();
      expect(tester.getBottomLeft(title).dy, lessThan(340));
      expect(tester.takeException(), isNull);
      FocusManager.instance.primaryFocus?.unfocus();
      tester.view.viewInsets = FakeViewPadding.zero;
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const ValueKey('analyzeButton')));
      expect(find.text('Analyze Song'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

class _FakeFileSelector implements AudioFileSelector {
  _FakeFileSelector(this.file);

  final File? file;

  @override
  Future<File?> chooseAudio() async => file;
}

class _FakePreparation implements AnalysisPracticePreparation {
  Completer<AnalyzedPracticeSession> _completer = Completer();
  AnalysisUploadProgress? _progress;
  AnalysisJobUpdate? _jobUpdate;
  int calls = 0;
  Object? nextError;
  final cancellations = <AnalysisPollingCancellationToken>[];

  @override
  Future<AnalyzedPracticeSession> prepare({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onUploadProgress,
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  }) {
    calls += 1;
    cancellations.add(cancellation!);
    _progress = onUploadProgress;
    _jobUpdate = onJobUpdated;
    final error = nextError;
    if (error != null) {
      nextError = null;
      return Future<AnalyzedPracticeSession>.error(error);
    }
    return _completer.future;
  }

  void emitProgress(int sent, int total) => _progress?.call(sent, total);
  void emitJob(AnalysisJobStatus status) => _jobUpdate?.call(_job(status));

  void complete(AnalyzedPracticeSession session) {
    _completer.complete(session);
    _completer = Completer();
  }
}

AnalysisJob _job(AnalysisJobStatus status) => AnalysisJob(
  jobId: 'widget-job',
  status: status,
  createdAt: DateTime.utc(2026),
  updatedAt: DateTime.utc(2026),
  error: null,
  resultAvailable: status == AnalysisJobStatus.completed,
);

AnalyzedPracticeSession _session(File audio) => AnalyzedPracticeSession(
  title: 'safe_song',
  job: _job(AnalysisJobStatus.completed),
  audioFile: audio,
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
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
        ],
      ),
    ],
    lyrics: [],
  ),
);
