import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
import 'package:chordsync/features/analysis/presentation/audio_import_controller.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory directory;
  late File audio;
  late _FakePreparation preparation;
  late AudioImportController controller;

  setUp(() {
    directory = Directory.systemTemp.createTempSync('chordsync-import-test-');
    audio = File('${directory.path}/my_song.mp3')..writeAsBytesSync([1, 2, 3]);
    preparation = _FakePreparation();
    controller = AudioImportController(preparation: preparation);
  });

  tearDown(() {
    controller.dispose();
    directory.deleteSync(recursive: true);
  });

  test('starts idle and selects safe file metadata with derived title', () {
    expect(controller.phase, AudioImportPhase.idle);
    expect(controller.canAnalyze, isFalse);

    expect(controller.selectFile(audio), isTrue);

    expect(controller.phase, AudioImportPhase.fileSelected);
    expect(controller.filename, 'my_song.mp3');
    expect(controller.extension, 'mp3');
    expect(controller.fileSizeBytes, 3);
    expect(controller.title, 'my_song');
    expect(controller.canAnalyze, isTrue);
  });

  test('uses source display name while retaining the opaque stored file', () {
    final stored = File(
      '${directory.path}/0123456789abcdef0123456789abcdef.wav',
    )..writeAsBytesSync([1, 2, 3]);

    expect(
      controller.selectFile(stored, displayName: 'My Practice Song.WAV'),
      isTrue,
    );

    expect(controller.selectedFile, stored);
    expect(controller.filename, 'My Practice Song.WAV');
    expect(controller.extension, 'wav');
    expect(controller.title, 'My Practice Song');
  });

  test('rejects unsupported files without exposing their path', () {
    final unsupported = File('${directory.path}/private_notes.txt')
      ..writeAsStringSync('not audio');

    expect(controller.selectFile(unsupported), isFalse);
    expect(controller.phase, AudioImportPhase.failed);
    expect(controller.errorMessage, 'Choose a WAV, MP3, or M4A audio file.');
    expect(controller.errorMessage, isNot(contains(directory.path)));
  });

  test('validates and trims the editable backend title', () async {
    controller.selectFile(audio);
    controller.setTitle('   ');
    expect(controller.canAnalyze, isFalse);
    controller.setTitle(List.filled(201, 'x').join());
    expect(controller.canAnalyze, isFalse);
    controller.setTitle('  Custom practice  ');
    expect(controller.canAnalyze, isTrue);

    final analysis = controller.analyze();
    expect(preparation.titles.single, 'Custom practice');
    preparation.complete(_session(audio));
    await analysis;
  });

  test('reports upload, job, preparation, and completed states', () async {
    controller.selectFile(audio);
    final analysis = controller.analyze();
    expect(controller.phase, AudioImportPhase.uploading);

    preparation.emitProgress(42, 100);
    expect(controller.uploadProgress, 0.42);
    expect(controller.phase, AudioImportPhase.uploading);
    preparation.emitProgress(100, 100);
    expect(controller.phase, AudioImportPhase.finishingUpload);
    preparation.emitJob(AnalysisJobStatus.queued);
    expect(controller.phase, AudioImportPhase.queued);
    preparation.emitJob(AnalysisJobStatus.processing);
    expect(controller.phase, AudioImportPhase.processing);
    preparation.emitJob(AnalysisJobStatus.completed);
    expect(controller.phase, AudioImportPhase.preparing);

    final session = _session(audio);
    preparation.complete(session);
    await analysis;

    expect(controller.phase, AudioImportPhase.ready);
    expect(controller.session, same(session));
    expect(preparation.files.single, same(audio));
    expect(preparation.titles.single, 'my_song');
  });

  test('saves a completed analysis for later practice', () async {
    final library = _FakeSessionLibrary();
    controller.dispose();
    controller = AudioImportController(
      preparation: preparation,
      sessionLibrary: library,
    );
    controller.selectFile(audio);

    final analysis = controller.analyze();
    final session = _session(audio);
    preparation.complete(session);
    await analysis;

    expect(library.saved, [same(session)]);
    expect(controller.phase, AudioImportPhase.ready);
  });

  test('reset returns a completed import to the source screen state', () async {
    controller.selectFile(audio);
    final analysis = controller.analyze();
    preparation.complete(_session(audio));
    await analysis;

    controller.reset();

    expect(controller.phase, AudioImportPhase.idle);
    expect(controller.selectedFile, isNull);
    expect(controller.filename, isNull);
    expect(controller.title, isEmpty);
    expect(controller.session, isNull);
    expect(controller.canAnalyze, isFalse);
  });

  test('guards duplicate analyze and file changes while active', () async {
    controller.selectFile(audio);
    final first = controller.analyze();
    final second = controller.analyze();
    final other = File('${directory.path}/other.wav')..writeAsBytesSync([4]);

    expect(controller.selectFile(other), isFalse);
    expect(preparation.calls, 1);

    preparation.complete(_session(audio));
    await Future.wait([first, second]);
    expect(preparation.calls, 1);
  });

  test('cancels local waiting and keeps selection for retry', () async {
    controller.selectFile(audio);
    final first = controller.analyze();

    controller.cancel();
    expect(preparation.cancellations.single.isCancelled, isTrue);
    expect(controller.phase, AudioImportPhase.cancelled);
    preparation.fail(const AnalysisPollingCancelledException());
    await first;

    final retry = controller.analyze();
    expect(preparation.calls, 2);
    preparation.complete(_session(audio));
    await retry;
    expect(controller.phase, AudioImportPhase.ready);
  });

  test('maps typed errors to safe retryable messages', () async {
    controller.selectFile(audio);
    final analysis = controller.analyze();
    preparation.fail(
      const AnalysisApiException(
        statusCode: 413,
        code: 'audio_too_large',
        message: 'private backend detail',
      ),
    );
    await analysis;

    expect(controller.phase, AudioImportPhase.failed);
    expect(controller.errorMessage, 'The selected audio file is too large.');
    expect(controller.errorMessage, isNot(contains('private')));
    expect(controller.canAnalyze, isTrue);
  });

  test('dispose cancels active local waiting without later notifications', () {
    controller.selectFile(audio);
    unawaited(controller.analyze());

    controller.dispose();

    expect(preparation.cancellations.single.isCancelled, isTrue);
  });

  test(
    'hosted-only job states map onto the existing progress phases',
    () async {
      controller
        ..selectFile(audio)
        ..setTitle('Song');
      unawaited(controller.analyze());
      await Future<void>.delayed(Duration.zero);

      preparation.emitJob(AnalysisJobStatus.awaitingUpload);
      expect(controller.phase, AudioImportPhase.uploading);
      preparation.emitJob(AnalysisJobStatus.validating);
      expect(controller.phase, AudioImportPhase.queued);
      preparation.emitJob(AnalysisJobStatus.queued);
      expect(controller.phase, AudioImportPhase.queued);
      preparation.emitJob(AnalysisJobStatus.processing);
      expect(controller.phase, AudioImportPhase.processing);

      preparation.fail(const AnalysisPollingCancelledException());
      await Future<void>.delayed(Duration.zero);
    },
  );

  group('hosted errors become safe messages', () {
    Future<String?> messageFor(Object error) async {
      controller
        ..selectFile(audio)
        ..setTitle('Song');
      final run = controller.analyze();
      await Future<void>.delayed(Duration.zero);
      preparation.fail(error);
      await run;
      expect(controller.phase, AudioImportPhase.failed);
      final message = controller.errorMessage;
      controller.reset();
      return message;
    }

    test('authentication', () async {
      for (final error in [
        const AnalysisApiException(
          statusCode: 401,
          code: 'unauthorized',
          message: 'x',
        ),
        const AnalysisApiException(
          statusCode: 401,
          code: 'authentication_required',
          message: 'x',
        ),
      ]) {
        expect(await messageFor(error), contains('access token'));
      }
    });

    test('upload failures', () async {
      expect(
        await messageFor(
          const AnalysisUploadException(AnalysisUploadFailure.urlExpired, 'm'),
        ),
        contains('try again'),
      );
      expect(
        await messageFor(
          const AnalysisUploadException(AnalysisUploadFailure.timeout, 'm'),
        ),
        contains('timed out'),
      );
      expect(
        await messageFor(
          const AnalysisUploadException(AnalysisUploadFailure.connection, 'm'),
        ),
        contains("can't reach"),
      );
      expect(
        await messageFor(
          const AnalysisUploadException(AnalysisUploadFailure.rejected, 'm'),
        ),
        contains('not accepted'),
      );
    });

    test('backend validation and availability codes', () async {
      for (final (code, fragment) in [
        ('audio_too_long', '6 minutes'),
        ('invalid_audio', 'could not be read'),
        ('empty_audio', 'could not be read'),
        ('upload_not_received', 'did not finish'),
        ('upload_expired', 'expired'),
        ('service_unavailable', 'temporarily unavailable'),
      ]) {
        final message = await messageFor(
          AnalysisApiException(
            statusCode: 422,
            code: code,
            message: 'internal detail',
          ),
        );
        expect(message, contains(fragment), reason: code);
        expect(message, isNot(contains('internal detail')));
      }
    });

    test('messages never contain a URL or the file path', () async {
      final message = await messageFor(
        const AnalysisUploadException(
          AnalysisUploadFailure.rejected,
          'https://bucket.s3.amazonaws.com/x?X-Amz-Signature=secret',
        ),
      );
      expect(message, isNot(contains('amazonaws')));
      expect(message, isNot(contains('Signature')));
      expect(message, isNot(contains(directory.path)));
    });
  });
}

class _FakeSessionLibrary implements AnalyzedSessionLibrary {
  final saved = <AnalyzedPracticeSession>[];

  @override
  Future<List<AnalyzedPracticeSession>> load() async => saved;

  @override
  Future<void> save(AnalyzedPracticeSession session) async =>
      saved.add(session);
}

class _FakePreparation implements AnalysisPracticePreparation {
  Completer<AnalyzedPracticeSession> _completer = Completer();
  AnalysisUploadProgress? _progress;
  AnalysisJobUpdate? _jobUpdate;
  int calls = 0;
  final files = <File>[];
  final titles = <String>[];
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
    files.add(audioFile);
    titles.add(title);
    cancellations.add(cancellation!);
    _progress = onUploadProgress;
    _jobUpdate = onJobUpdated;
    return _completer.future;
  }

  void emitProgress(int sent, int total) => _progress?.call(sent, total);

  void emitJob(AnalysisJobStatus status) => _jobUpdate?.call(_job(status));

  void complete(AnalyzedPracticeSession session) {
    _completer.complete(session);
    _completer = Completer();
  }

  void fail(Object error) {
    _completer.completeError(error);
    _completer = Completer();
  }
}

AnalysisJob _job(AnalysisJobStatus status) => AnalysisJob(
  jobId: 'job-one',
  status: status,
  createdAt: DateTime.utc(2026),
  updatedAt: DateTime.utc(2026),
  error: null,
  resultAvailable: status == AnalysisJobStatus.completed,
);

AnalyzedPracticeSession _session(File audio) => AnalyzedPracticeSession(
  title: 'my_song',
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
        endTime: 1,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
        ],
      ),
    ],
    lyrics: [],
  ),
);
