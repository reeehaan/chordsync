import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/application/analysis_practice_coordinator.dart';
import 'package:chordsync/features/analysis/application/hosted_analysis_client.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/hosted_analysis_api.dart';
import 'package:chordsync/features/analysis/data/hosted_upload_models.dart';
import 'package:chordsync/features/analysis/data/presigned_uploader.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/recording_http_adapter.dart';

AnalysisJob _job(String status, {String id = 'job-1'}) =>
    AnalysisJob.fromJson(hostedJobJson(status, id: id));

class _FakeApi implements HostedAnalysisApi {
  _FakeApi(this.events);

  final List<String> events;
  CreateUploadRequest? created;
  final confirmResults =
      <Object>[]; // an exception is thrown, a job is returned
  int confirmCalls = 0;
  Object? createError;
  final cancelCalls = <String>[];
  Object? cancelError;
  final getJobErrors = <Exception>[];
  final getResultErrors = <Exception>[];
  int getJobCalls = 0;

  @override
  Future<UploadTarget> createUpload(CreateUploadRequest request) async {
    events.add('create');
    created = request;
    if (createError != null) throw createError!;
    return UploadTarget.fromJson(uploadTargetJson());
  }

  @override
  Future<ConfirmOutcome> confirmUpload(String jobId) async {
    events.add('confirm');
    confirmCalls++;
    final next = confirmResults.isEmpty
        ? _job('queued')
        : confirmResults.removeAt(0);
    if (next is Exception) throw next;
    return ConfirmOutcome(job: next as AnalysisJob, newlyQueued: true);
  }

  @override
  Future<AnalysisJob> cancelJob(String jobId) async {
    events.add('cancel');
    cancelCalls.add(jobId);
    if (cancelError case final Object error) throw error;
    return _job('cancelled', id: jobId);
  }

  @override
  Future<AnalysisJob> getJob(String jobId) async {
    getJobCalls++;
    if (getJobErrors.isNotEmpty) throw getJobErrors.removeAt(0);
    return _job('completed');
  }

  @override
  Future<SharedTimeline> getResult(String jobId) async {
    if (getResultErrors.isNotEmpty) throw getResultErrors.removeAt(0);
    return SharedTimeline.fromJson(hostedTimelineJson);
  }
}

class _FakeUploader implements PresignedUploader {
  _FakeUploader(this.events);

  final List<String> events;
  UploadTarget? target;
  Object? error;
  Completer<void>? hold;
  void Function()? afterUpload;
  int progressTotal = 0;

  @override
  Future<void> upload({
    required UploadTarget target,
    required File file,
    UploadProgress? onProgress,
    CancelToken? cancelToken,
  }) async {
    events.add('upload');
    this.target = target;
    final length = await file.length();
    onProgress?.call(length, length);
    progressTotal = length;
    if (hold != null) {
      await Future.any([hold!.future, cancelToken!.whenCancel]);
      if (cancelToken.isCancelled) {
        throw const AnalysisPollingCancelledException();
      }
    }
    if (error != null) throw error!;
    afterUpload?.call();
  }
}

AnalysisApiException _apiError(int status, String code) =>
    AnalysisApiException(statusCode: status, code: code, message: 'm');

void main() {
  late Directory directory;
  late List<String> events;
  late _FakeApi api;
  late _FakeUploader uploader;
  late List<Duration> delays;
  late HostedAnalysisClient client;

  Future<File> audio(String name, List<int> bytes) async {
    final file = File('${directory.path}/$name');
    await file.writeAsBytes(bytes);
    return file;
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('chordsync-hosted-');
    events = [];
    api = _FakeApi(events);
    uploader = _FakeUploader(events);
    delays = [];
    client = HostedAnalysisClient(
      api: api,
      uploader: uploader,
      confirmAttempts: 3,
      confirmRetryDelay: const Duration(seconds: 1),
      delay: (d) async => delays.add(d),
      cancelCheckInterval: const Duration(milliseconds: 5),
    );
  });

  tearDown(() => directory.delete(recursive: true));

  group('submit', () {
    test('creates, uploads, then confirms, in that order', () async {
      final file = await audio('song.wav', [1, 2, 3, 4, 5, 6, 7]);
      final progress = <(int, int)>[];

      final job = await client.createJob(
        title: 'Song',
        audioFile: file,
        onSendProgress: (s, t) => progress.add((s, t)),
      );

      expect(events, ['create', 'upload', 'confirm']);
      expect(job.status, AnalysisJobStatus.queued);
      expect(api.created!.filename, 'song.wav');
      expect(api.created!.declaredSizeBytes, 7);
      expect(api.created!.contentType, 'audio/wav');
      expect(uploader.target!.jobId, 'job-1');
      expect(progress, [(7, 7)]);
    });

    test('maps each supported extension to its content type', () async {
      for (final (name, type) in [
        ('a.mp3', 'audio/mpeg'),
        ('a.M4A', 'audio/mp4'),
        ('a.wav', 'audio/wav'),
      ]) {
        await client.createJob(title: 't', audioFile: await audio(name, [1]));
        expect(api.created!.contentType, type);
      }
    });

    test('the declared size is the real size on disk', () async {
      final file = await audio('big.mp3', List.filled(12345, 1));
      await client.createJob(title: 't', audioFile: file);
      expect(api.created!.declaredSizeBytes, 12345);
    });
  });

  group('validation before any network call', () {
    test('unsupported extensions', () async {
      for (final name in ['song.flac', 'song', 'song.mp3.exe']) {
        await expectLater(
          client.createJob(title: 't', audioFile: await audio(name, [1])),
          throwsA(
            isA<AnalysisApiException>().having(
              (e) => e.code,
              'code',
              'unsupported_audio_format',
            ),
          ),
        );
      }
      expect(events, isEmpty);
    });

    test('empty files', () async {
      await expectLater(
        client.createJob(title: 't', audioFile: await audio('e.wav', [])),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.code,
            'code',
            'empty_audio',
          ),
        ),
      );
      expect(events, isEmpty);
    });

    test('files over 25 MB', () async {
      final file = File('${directory.path}/huge.wav');
      final handle = await file.open(mode: FileMode.write);
      await handle.setPosition(
        maxAnalysisUploadBytes,
      ); // sparse: size 25 MiB + 1
      await handle.writeByte(0);
      await handle.close();
      await expectLater(
        client.createJob(title: 't', audioFile: file),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.code,
            'code',
            'audio_too_large',
          ),
        ),
      );
      expect(events, isEmpty);
    });

    test('exactly 25 MB is allowed', () async {
      final file = File('${directory.path}/limit.wav');
      final handle = await file.open(mode: FileMode.write);
      await handle.setPosition(maxAnalysisUploadBytes - 1);
      await handle.writeByte(0);
      await handle.close();
      await client.createJob(title: 't', audioFile: file);
      expect(api.created!.declaredSizeBytes, maxAnalysisUploadBytes);
    });

    test('a missing file', () async {
      await expectLater(
        client.createJob(
          title: 't',
          audioFile: File('${directory.path}/gone.wav'),
        ),
        throwsA(isA<AnalysisDataException>()),
      );
      expect(events, isEmpty);
    });
  });

  group('failures stop the flow at the right place', () {
    test('a failed create sends no upload and no confirm', () async {
      api.createError = _apiError(401, 'unauthorized');
      await expectLater(
        client.createJob(title: 't', audioFile: await audio('a.wav', [1])),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.isUnauthorized,
            'u',
            true,
          ),
        ),
      );
      expect(events, ['create']);
    });

    test('a failed upload is never confirmed', () async {
      uploader.error = const AnalysisUploadException(
        AnalysisUploadFailure.urlExpired,
        'expired',
      );
      await expectLater(
        client.createJob(title: 't', audioFile: await audio('a.wav', [1])),
        throwsA(isA<AnalysisUploadException>()),
      );
      expect(events, ['create', 'upload']);
    });

    test('a hidden 404 or 401 on confirm is not retried', () async {
      for (final error in [
        _apiError(404, 'job_not_found'),
        _apiError(401, 'unauthorized'),
      ]) {
        api.confirmResults.add(error);
        events.clear();
        await expectLater(
          client.createJob(title: 't', audioFile: await audio('a.wav', [1])),
          throwsA(isA<AnalysisApiException>()),
        );
        expect(events.where((e) => e == 'confirm'), hasLength(1));
      }
      expect(delays, isEmpty);
    });
  });

  group('confirm retry', () {
    test('upload_not_received is retried, then succeeds', () async {
      api.confirmResults.addAll([
        _apiError(409, 'upload_not_received'),
        _job('queued'),
      ]);
      final job = await client.createJob(
        title: 't',
        audioFile: await audio('a.wav', [1]),
      );
      expect(job.status, AnalysisJobStatus.queued);
      expect(api.confirmCalls, 2);
      expect(delays, [const Duration(seconds: 1)]);
    });

    test('gives up after the configured attempts and reports it', () async {
      api.confirmResults.addAll(
        List.filled(5, _apiError(409, 'upload_not_received')),
      );
      await expectLater(
        client.createJob(title: 't', audioFile: await audio('a.wav', [1])),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.code,
            'code',
            'upload_not_received',
          ),
        ),
      );
      expect(api.confirmCalls, 3);
    });

    test('other 409 or 503 errors are not retried', () async {
      for (final error in [
        _apiError(409, 'invalid_job_state'),
        _apiError(503, 'service_unavailable'),
      ]) {
        api.confirmCalls = 0;
        api.confirmResults.add(error);
        await expectLater(
          client.createJob(title: 't', audioFile: await audio('a.wav', [1])),
          throwsA(isA<AnalysisApiException>()),
        );
        expect(api.confirmCalls, 1);
      }
    });

    test('a repeated confirm that returns a later state is fine', () async {
      api.confirmResults.add(_job('processing'));
      final job = await client.createJob(
        title: 't',
        audioFile: await audio('a.wav', [1]),
      );
      expect(job.status, AnalysisJobStatus.processing);
    });
  });

  group('cancellation', () {
    test('cancelled before starting: nothing is sent', () async {
      final token = AnalysisPollingCancellationToken()..cancel();
      await expectLater(
        client.createJob(
          title: 't',
          audioFile: await audio('a.wav', [1]),
          cancellation: token,
        ),
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(events, isEmpty);
      expect(api.cancelCalls, isEmpty);
    });

    test('cancelling during the upload also cancels the job', () async {
      uploader.hold = Completer<void>();
      final token = AnalysisPollingCancellationToken();
      final result = client.createJob(
        title: 't',
        audioFile: await audio('a.wav', [1]),
        cancellation: token,
      );
      await Future<void>.delayed(const Duration(milliseconds: 30));
      token.cancel();
      await expectLater(
        result,
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(events, ['create', 'upload', 'cancel']);
      expect(api.cancelCalls, ['job-1']);
    });

    test('an unreachable server still reports the cancellation', () async {
      final token = AnalysisPollingCancellationToken();
      uploader.afterUpload = token.cancel;
      api.cancelError = const AnalysisTransportException('offline');
      await expectLater(
        client.createJob(
          title: 't',
          audioFile: await audio('a.wav', [1]),
          cancellation: token,
        ),
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(api.cancelCalls, ['job-1']);
    });

    test('cancelJob forwards to the API', () async {
      await client.cancelJob('job-7');
      expect(api.cancelCalls, ['job-7']);
    });

    test('cancelling during the upload stops it and skips confirm', () async {
      uploader.hold = Completer<void>();
      final token = AnalysisPollingCancellationToken();
      final result = client.createJob(
        title: 't',
        audioFile: await audio('a.wav', [1]),
        cancellation: token,
      );
      await Future<void>.delayed(const Duration(milliseconds: 30));
      token.cancel();
      await expectLater(
        result,
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(events, ['create', 'upload', 'cancel']);
    });

    test('cancelled between upload and confirm: not confirmed', () async {
      final token = AnalysisPollingCancellationToken();
      uploader.afterUpload = token.cancel;
      await expectLater(
        client.createJob(
          title: 't',
          audioFile: await audio('a.wav', [1]),
          cancellation: token,
        ),
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(events, ['create', 'upload', 'cancel']);
    });
  });

  group('whole workflow through the real coordinator and poller', () {
    test('submit, poll and fetch produce a practice session', () async {
      final polling = AnalysisJobPoller(
        client: client,
        pollingInterval: const Duration(milliseconds: 1),
        delay: (_) async {},
      );
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: polling,
      );
      final file = await audio('song.wav', [1, 2, 3, 4, 5, 6, 7]);
      final updates = <AnalysisJobStatus>[];

      final session = await coordinator.prepare(
        title: 'My song',
        audioFile: file,
        onJobUpdated: (job) => updates.add(job.status),
      );

      expect(events, ['create', 'upload', 'confirm']);
      expect(session.title, 'My song');
      expect(session.timeline.bpm, 90.0);
      expect(session.audioFile, same(file));
      expect(updates, [AnalysisJobStatus.queued, AnalysisJobStatus.completed]);
    });

    test('polling retries never create a second job or re-upload', () async {
      api.getJobErrors.addAll([
        _apiError(429, 'rate_limited'),
        _apiError(503, 'service_unavailable'),
      ]);
      api.getResultErrors.add(_apiError(409, 'result_not_ready'));
      final polling = AnalysisJobPoller(
        client: client,
        pollingInterval: const Duration(milliseconds: 1),
        delay: (_) async {},
      );
      final coordinator = AnalysisPracticeCoordinator(
        client: client,
        polling: polling,
      );
      final file = await audio('song.wav', [1, 2, 3, 4, 5, 6, 7]);

      final session = await coordinator.prepare(title: 'Song', audioFile: file);

      expect(session.timeline.bpm, 90.0);
      expect(events, ['create', 'upload', 'confirm']);
      expect(api.getJobCalls, greaterThan(2));
    });

    test(
      'awaiting_upload and validating are treated as still waiting',
      () async {
        var polls = 0;
        final waitingApi = _SequenceApi([
          _job('awaiting_upload'),
          _job('validating'),
          _job('queued'),
          _job('processing'),
          _job('completed'),
        ], () => polls++);
        final waitingClient = HostedAnalysisClient(
          api: waitingApi,
          uploader: uploader,
        );
        final polling = AnalysisJobPoller(
          client: waitingClient,
          pollingInterval: const Duration(milliseconds: 1),
          delay: (_) async {},
        );
        final result = await polling.pollUntilComplete('job-1');
        expect(result.job.status, AnalysisJobStatus.completed);
        expect(polls, 5);
      },
    );

    test('a failed job surfaces the backend error code', () async {
      final failing = _SequenceApi([
        AnalysisJob.fromJson({
          ...hostedJobJson('failed'),
          'error': {
            'code': 'invalid_audio',
            'message': 'Audio could not be decoded.',
          },
        }),
      ], () {});
      final polling = AnalysisJobPoller(
        client: HostedAnalysisClient(api: failing, uploader: uploader),
        pollingInterval: const Duration(milliseconds: 1),
        delay: (_) async {},
      );
      await expectLater(
        polling.pollUntilComplete('job-1'),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.code,
            'code',
            'invalid_audio',
          ),
        ),
      );
    });
  });

  group('real clients end to end (HTTP faked)', () {
    test('the bearer token goes to the API only, never to storage', () async {
      const token = 'end-to-end-token-0123456789abcdef';
      final file = await audio('song.wav', [1, 2, 3, 4, 5, 6, 7]);
      final apiAdapter = RecordingHttpAdapter((r) {
        if (r.uri.path == '/analysis/jobs') {
          return jsonBody(uploadTargetJson(), 201);
        }
        return jsonBody(hostedJobJson('queued'), 202);
      });
      final storageAdapter = RecordingHttpAdapter(
        (_) => ResponseBody.fromString('', 200),
      );
      final real = HostedAnalysisClient(
        api: DioHostedAnalysisApi(
          baseUrl: 'https://api.test.invalid',
          tokenProvider: () => token,
          dio: dioWith(apiAdapter),
        ),
        uploader: DioPresignedUploader(dio: dioWith(storageAdapter)),
      );

      final job = await real.createJob(title: 'Song', audioFile: file);

      expect(job.status, AnalysisJobStatus.queued);
      expect(apiAdapter.requests.map((r) => r.uri.path), [
        '/analysis/jobs',
        '/analysis/jobs/job-1/confirm-upload',
      ]);
      expect(
        apiAdapter.requests.every(
          (r) => r.headers['Authorization'] == 'Bearer $token',
        ),
        isTrue,
      );
      final put = storageAdapter.requests.single;
      expect(put.method, 'PUT');
      expect(put.uri.host, 'bucket.s3.ap-southeast-1.amazonaws.com');
      expect(put.body, [1, 2, 3, 4, 5, 6, 7]);
      expect(
        put.headers.keys.map((k) => k.toLowerCase()),
        isNot(contains('authorization')),
      );
      for (final value in put.headers.values) {
        expect(value.toString(), isNot(contains(token)));
      }
      expect(put.uri.toString(), isNot(contains(token)));
    });
  });
}

class _SequenceApi implements HostedAnalysisApi {
  _SequenceApi(this.jobs, this.onPoll);

  final List<AnalysisJob> jobs;
  final void Function() onPoll;
  var _index = 0;

  @override
  Future<AnalysisJob> getJob(String jobId) async {
    onPoll();
    return jobs[_index < jobs.length ? _index++ : jobs.length - 1];
  }

  @override
  Future<SharedTimeline> getResult(String jobId) async =>
      SharedTimeline.fromJson(hostedTimelineJson);

  @override
  Future<UploadTarget> createUpload(CreateUploadRequest request) =>
      throw UnimplementedError();

  @override
  Future<ConfirmOutcome> confirmUpload(String jobId) =>
      throw UnimplementedError();

  @override
  Future<AnalysisJob> cancelJob(String jobId) => throw UnimplementedError();
}
