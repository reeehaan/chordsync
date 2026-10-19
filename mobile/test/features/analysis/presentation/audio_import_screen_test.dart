import 'dart:async';
import 'dart:io';

import 'package:chordsync/design_system/chordsync_design_system.dart';
import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
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

  Future<void> pumpScreen(
    WidgetTester tester, {
    AnalyzedSessionLibrary? sessionLibrary,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ChordSyncTheme.light(),
        home: AudioImportScreen(
          controller: controller,
          fileSelector: selector,
          practiceSessionFactory: PracticeSessionFactory(
            audioPlayerFactory: (_) => practicePlayer,
          ),
          sessionLibrary: sessionLibrary,
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('selects audio and presents upload through ready states', (
    tester,
  ) async {
    await pumpScreen(tester);

    expect(find.text('Upload'), findsOneWidget);
    // Golden Hour: dark brown text on the parchment page, readable.
    final title = tester.widget<Text>(find.text('Upload'));
    expect(title.style?.color, ChordSyncColors.textPrimary);
    expect(find.textContaining('WAV · MP3 · M4A'), findsOneWidget);
    expect(preparation.calls, 0);

    // Picking a valid file starts analysis immediately — there is no
    // separate confirmation step or manual "Analyze" action.
    final filesSource = find.byKey(const ValueKey('filesSource'));
    await tester.ensureVisible(filesSource);
    await tester.tap(filesSource);
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
    await tester.pumpAndSettle();
    expect(find.text('safe_song'), findsOneWidget);
    expect(find.byKey(const ValueKey('currentChordValue')), findsOneWidget);

    Navigator.of(tester.element(find.text('safe_song'))).pop();
    await tester.pumpAndSettle();
    expect(find.text('Upload'), findsOneWidget);
    expect(find.byKey(const ValueKey('filesSource')), findsOneWidget);
    expect(find.text('Ready to practice'), findsNothing);
    expect(find.text('safe_song.wav'), findsNothing);
  });

  testWidgets('shows song sources and explains Shazam behavior', (
    tester,
  ) async {
    await pumpScreen(tester);

    expect(find.byKey(const ValueKey('youtubeSource')), findsOneWidget);
    expect(find.byKey(const ValueKey('cameraRollSource')), findsOneWidget);
    expect(find.byKey(const ValueKey('filesSource')), findsOneWidget);
    expect(find.byKey(const ValueKey('recordSource')), findsOneWidget);
    expect(find.byKey(const ValueKey('shazamSource')), findsOneWidget);

    final shazamSource = find.byKey(const ValueKey('shazamSource'));
    await tester.ensureVisible(shazamSource);
    await tester.tap(shazamSource);
    await tester.pumpAndSettle();

    expect(find.text('Shazam'), findsWidgets);
    expect(
      find.textContaining('does not connect to it directly yet'),
      findsOneWidget,
    );
  });

  testWidgets('opens a previously analyzed song without analyzing again', (
    tester,
  ) async {
    final saved = _session(audio);
    await pumpScreen(tester, sessionLibrary: _FakeSessionLibrary([saved]));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('bottomNav0')));
    await tester.pumpAndSettle();

    expect(find.text('Previously analyzed'), findsOneWidget);
    expect(find.text('safe_song'), findsOneWidget);
    expect(find.text('1 saved'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('savedPractice-widget-job')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('currentChordValue')), findsOneWidget);
    expect(preparation.calls, 0);
  });

  testWidgets('bottom dock switches between Home, Add Song, and Tuner', (
    tester,
  ) async {
    await pumpScreen(tester);

    expect(find.text('Upload'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('bottomNav2')));
    await tester.pumpAndSettle();
    expect(find.text('Tuner'), findsOneWidget);
    expect(find.text('Microphone tuner coming next'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('bottomNav0')));
    await tester.pumpAndSettle();
    expect(find.text('Your songs'), findsOneWidget);
    expect(find.text('No analyzed songs yet'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('bottomNav1')));
    await tester.pumpAndSettle();
    expect(find.text('Upload'), findsOneWidget);
  });

  testWidgets('shows safe errors, supports retry, and cancels locally', (
    tester,
  ) async {
    await pumpScreen(tester);
    preparation.nextError = const AnalysisTransportException(
      'private host detail',
    );

    // Picking the file starts analysis itself, which fails immediately.
    final filesSource = find.byKey(const ValueKey('filesSource'));
    await tester.ensureVisible(filesSource);
    await tester.tap(filesSource);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    expect(preparation.calls, 1);
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
    expect(find.byKey(const ValueKey('retryAnalysisButton')), findsOneWidget);
    expect(find.text('safe_song.wav'), findsOneWidget);
  });

  testWidgets('shows a path-free error when audio import fails', (
    tester,
  ) async {
    await pumpScreen(tester);
    selector.error = FileSystemException(
      'private picker failure',
      '${directory.path}/private-song.wav',
    );

    final filesSource = find.byKey(const ValueKey('filesSource'));
    await tester.ensureVisible(filesSource);
    await tester.tap(filesSource);
    await tester.pump();

    expect(
      find.text('Could not import that audio file. Please try again.'),
      findsOneWidget,
    );
    expect(find.textContaining(directory.path), findsNothing);
    expect(tester.takeException(), isNull);
    expect(preparation.calls, 0);
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
      expect(find.byKey(const ValueKey('filesSource')), findsOneWidget);
      expect(find.text('Get the chords for any audio track'), findsOneWidget);
    }
  });
}

class _FakeFileSelector implements AudioFileSelector {
  _FakeFileSelector(this.file);

  final File? file;
  Object? error;

  @override
  Future<SelectedAudioFile?> chooseAudio() async {
    if (error case final failure?) throw failure;
    final selected = file;
    if (selected == null) return null;
    return SelectedAudioFile(
      file: selected,
      displayName: selected.uri.pathSegments.last,
    );
  }
}

class _FakeSessionLibrary implements AnalyzedSessionLibrary {
  _FakeSessionLibrary(this.sessions);

  final List<AnalyzedPracticeSession> sessions;

  @override
  Future<List<AnalyzedPracticeSession>> load() async => sessions;

  @override
  Future<void> save(AnalyzedPracticeSession session) async {}
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
