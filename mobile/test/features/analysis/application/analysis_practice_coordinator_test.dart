import 'dart:io';

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'completed analysis becomes a session with exact input identities',
    () async {
      final audio = await _audioFile('selected.wav');
      final timeline = _timeline(chord: 'C');
      final job = _job('job-one', AnalysisJobStatus.completed);
      final client = _FakeClient(
        createResult: _job('job-one', AnalysisJobStatus.queued),
      );
      final polling = _FakePolling(
        AnalysisCompletedResult(job: job, timeline: timeline),
      );
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: polling,
      );

      final session = await coordinator.prepare(
        title: 'Selected song',
        audioFile: audio,
      );

      expect(client.uploadedFiles.single, same(audio));
      expect(polling.jobIds, ['job-one']);
      expect(session.audioFile, same(audio));
      expect(session.audioFile.path, audio.path);
      expect(session.timeline, same(timeline));
      expect(session.job, same(job));
      expect(session.title, 'Selected song');
    },
  );

  for (final failure in <Object>[
    const AnalysisApiException(
      statusCode: 409,
      code: 'analysis_failed',
      message: 'Analysis could not be completed.',
    ),
    const AnalysisPollingTimeoutException(),
    const AnalysisPollingCancelledException(),
  ]) {
    test('${failure.runtimeType} prevents session creation', () async {
      final audio = await _audioFile('failure.wav');
      final client = _FakeClient(
        createResult: _job('failed-job', AnalysisJobStatus.queued),
      );
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: _FakePolling.failure(failure),
      );

      await expectLater(
        coordinator.prepare(title: 'Failure', audioFile: audio),
        throwsA(same(failure)),
      );
    });
  }

  test('local audio disappearing after analysis fails safely', () async {
    final audio = await _audioFile('disappears.wav');
    final client = _FakeClient(
      createResult: _job('completed-job', AnalysisJobStatus.queued),
    );
    final polling = _FakePolling(
      AnalysisCompletedResult(
        job: _job('completed-job', AnalysisJobStatus.completed),
        timeline: _timeline(chord: 'G'),
      ),
      beforeReturn: audio.delete,
    );
    final coordinator = AnalysisPracticeCoordinator(
      client: client,
      polling: polling,
    );

    await expectLater(
      coordinator.prepare(title: 'Gone', audioFile: audio),
      throwsA(
        isA<PracticePreparationException>().having(
          (error) => error.code,
          'code',
          PracticePreparationErrorCode.localAudioUnavailable,
        ),
      ),
    );
    expect(client.uploadedFiles.single, same(audio));
  });

  test(
    'incompatible completed timeline fails before practice creation',
    () async {
      final audio = await _audioFile('incompatible.wav');
      final client = _FakeClient(
        createResult: _job('invalid-job', AnalysisJobStatus.queued),
      );
      final invalidTimeline = SharedTimeline(
        schemaVersion: 2,
        bpm: 120,
        beatsPerBar: 4,
        beatSource: 'test',
        lyricSource: 'none',
        bars: _timeline(chord: 'C').bars,
        lyrics: const [],
      );
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: _FakePolling(
          AnalysisCompletedResult(
            job: _job('invalid-job', AnalysisJobStatus.completed),
            timeline: invalidTimeline,
          ),
        ),
      );

      await expectLater(
        coordinator.prepare(title: 'Invalid', audioFile: audio),
        throwsA(
          isA<PracticePreparationException>().having(
            (error) => error.code,
            'code',
            PracticePreparationErrorCode.timelineIncompatible,
          ),
        ),
      );
    },
  );

  test(
    'concurrent preparations do not cross audio or timeline pairs',
    () async {
      final firstAudio = await _audioFile('first.wav');
      final secondAudio = await _audioFile('second.wav');
      final firstTimeline = _timeline(chord: 'C');
      final secondTimeline = _timeline(chord: 'G');
      final client = _FakeClient(
        createByPath: {
          firstAudio.path: _job('first-job', AnalysisJobStatus.queued),
          secondAudio.path: _job('second-job', AnalysisJobStatus.queued),
        },
      );
      final polling = _FakePolling.byJob({
        'first-job': AnalysisCompletedResult(
          job: _job('first-job', AnalysisJobStatus.completed),
          timeline: firstTimeline,
        ),
        'second-job': AnalysisCompletedResult(
          job: _job('second-job', AnalysisJobStatus.completed),
          timeline: secondTimeline,
        ),
      });
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: polling,
      );

      final sessions = await Future.wait([
        coordinator.prepare(title: 'First', audioFile: firstAudio),
        coordinator.prepare(title: 'Second', audioFile: secondAudio),
      ]);

      expect(sessions[0].audioFile, same(firstAudio));
      expect(sessions[0].timeline, same(firstTimeline));
      expect(sessions[0].job.jobId, 'first-job');
      expect(sessions[1].audioFile, same(secondAudio));
      expect(sessions[1].timeline, same(secondTimeline));
      expect(sessions[1].job.jobId, 'second-job');
    },
  );
}

class _FakeClient implements AnalysisApiClient {
  _FakeClient({this.createResult, this.createByPath = const {}});

  final AnalysisJob? createResult;
  final Map<String, AnalysisJob> createByPath;
  final uploadedFiles = <File>[];

  @override
  Future<AnalysisJob> createJob({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onSendProgress,
  }) async {
    uploadedFiles.add(audioFile);
    return createByPath[audioFile.path] ?? createResult!;
  }

  @override
  Future<AnalysisJob> getJob(String jobId) => throw UnimplementedError();

  @override
  Future<SharedTimeline> getResult(String jobId) => throw UnimplementedError();
}

class _FakePolling implements AnalysisJobPolling {
  _FakePolling(this.result, {this.beforeReturn})
    : error = null,
      results = const {};

  _FakePolling.failure(this.error)
    : result = null,
      results = const {},
      beforeReturn = null;

  _FakePolling.byJob(this.results)
    : result = null,
      error = null,
      beforeReturn = null;

  final AnalysisCompletedResult? result;
  final Object? error;
  final Map<String, AnalysisCompletedResult> results;
  final Future<void> Function()? beforeReturn;
  final jobIds = <String>[];

  @override
  Future<AnalysisCompletedResult> pollUntilComplete(
    String jobId, {
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  }) async {
    jobIds.add(jobId);
    if (error case final Object error) throw error;
    await beforeReturn?.call();
    final completed = results[jobId] ?? result!;
    onJobUpdated?.call(completed.job);
    return completed;
  }
}

Future<File> _audioFile(String name) async {
  final directory = await Directory.systemTemp.createTemp(
    'chordsync-session-test-',
  );
  return File('${directory.path}/$name').writeAsBytes([1, 2, 3]);
}

AnalysisJob _job(String id, AnalysisJobStatus status) => AnalysisJob(
  jobId: id,
  status: status,
  createdAt: DateTime.utc(2026),
  updatedAt: DateTime.utc(2026),
  error: null,
  resultAvailable: status == AnalysisJobStatus.completed,
);

SharedTimeline _timeline({required String chord}) => SharedTimeline(
  schemaVersion: 1,
  bpm: 120,
  beatsPerBar: 4,
  beatSource: 'synthetic',
  lyricSource: 'synthetic',
  bars: [
    TimelineBar(
      barNumber: 1,
      startTime: 0,
      endTime: 1,
      beats: [
        TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: chord),
      ],
    ),
  ],
  lyrics: const [],
);
