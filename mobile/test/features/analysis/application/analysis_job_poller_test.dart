import 'dart:io';

import 'package:chordsync/features/analysis/application/analysis_job_poller.dart';
import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

AnalysisJob job(
  String jobId,
  AnalysisJobStatus status, {
  AnalysisJobError? error,
}) => AnalysisJob(
  jobId: jobId,
  status: status,
  createdAt: DateTime.utc(2026, 9, 15),
  updatedAt: DateTime.utc(2026, 9, 15),
  error: error,
  resultAvailable: status == AnalysisJobStatus.completed,
);

SharedTimeline timeline(String chord) => SharedTimeline.fromJson({
  'schema_version': 1,
  'bpm': 120.0,
  'beats_per_bar': 4,
  'beat_source': 'synthetic',
  'lyric_source': 'synthetic',
  'bars': [
    {
      'bar_number': 1,
      'start_time': 0.0,
      'end_time': 1.0,
      'beats': [
        {'time': 0.0, 'beat_number': 1, 'is_downbeat': true, 'chord': chord},
      ],
    },
  ],
  'lyrics': <Object>[],
});

class FakeAnalysisApiClient implements AnalysisApiClient {
  FakeAnalysisApiClient({required this.statuses, required this.results});

  final Map<String, List<AnalysisJob>> statuses;
  final Map<String, SharedTimeline> results;
  final statusRequests = <String>[];
  final resultRequests = <String>[];

  /// Errors thrown (in order) before the next status/result requests succeed.
  final jobErrors = <Exception>[];
  final resultErrors = <Exception>[];

  @override
  Future<AnalysisJob> createJob({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onSendProgress,
    AnalysisPollingCancellationToken? cancellation,
  }) => throw UnimplementedError();

  @override
  Future<AnalysisJob> getJob(String jobId) async {
    statusRequests.add(jobId);
    if (jobErrors.isNotEmpty) throw jobErrors.removeAt(0);
    final queue = statuses[jobId]!;
    return queue.length == 1 ? queue.single : queue.removeAt(0);
  }

  final cancelRequests = <String>[];

  @override
  Future<void> cancelJob(String jobId) async => cancelRequests.add(jobId);

  @override
  Future<SharedTimeline> getResult(String jobId) async {
    resultRequests.add(jobId);
    if (resultErrors.isNotEmpty) throw resultErrors.removeAt(0);
    return results[jobId]!;
  }
}

AnalysisApiException apiError(int status, String code) =>
    AnalysisApiException(statusCode: status, code: code, message: 'm');

void main() {
  test('polls queued to processing to completed then fetches result', () async {
    final client = FakeAnalysisApiClient(
      statuses: {
        'job-1': [
          job('job-1', AnalysisJobStatus.queued),
          job('job-1', AnalysisJobStatus.processing),
          job('job-1', AnalysisJobStatus.completed),
        ],
      },
      results: {'job-1': timeline('C')},
    );
    final delays = <Duration>[];
    final updates = <AnalysisJobStatus>[];
    final poller = AnalysisJobPoller(
      client: client,
      pollingInterval: const Duration(seconds: 1),
      timeout: const Duration(minutes: 10),
      delay: (duration) async => delays.add(duration),
    );

    final completion = await poller.pollUntilComplete(
      'job-1',
      onJobUpdated: (job) => updates.add(job.status),
    );

    expect(completion.job.status, AnalysisJobStatus.completed);
    expect(completion.timeline.bars.single.beats.single.chord, 'C');
    expect(delays, [const Duration(seconds: 1), const Duration(seconds: 1)]);
    expect(updates, [
      AnalysisJobStatus.queued,
      AnalysisJobStatus.processing,
      AnalysisJobStatus.completed,
    ]);
    expect(client.resultRequests, ['job-1']);
  });

  test(
    'failed job stops immediately and surfaces safe backend failure',
    () async {
      final client = FakeAnalysisApiClient(
        statuses: {
          'job-1': [
            job(
              'job-1',
              AnalysisJobStatus.failed,
              error: const AnalysisJobError(
                code: 'analysis_failed',
                message: 'Analysis could not be completed.',
              ),
            ),
          ],
        },
        results: {},
      );
      final poller = AnalysisJobPoller(client: client, delay: (_) async {});

      await expectLater(
        poller.pollUntilComplete('job-1'),
        throwsA(
          isA<AnalysisApiException>()
              .having((error) => error.code, 'code', 'analysis_failed')
              .having(
                (error) => error.message,
                'message',
                'Analysis could not be completed.',
              ),
        ),
      );
      expect(client.statusRequests, ['job-1']);
      expect(client.resultRequests, isEmpty);
    },
  );

  test(
    'overall timeout prevents infinite polling without failing backend',
    () async {
      final client = FakeAnalysisApiClient(
        statuses: {
          'job-1': [job('job-1', AnalysisJobStatus.queued)],
        },
        results: {},
      );
      final delays = <Duration>[];
      final poller = AnalysisJobPoller(
        client: client,
        pollingInterval: const Duration(seconds: 1),
        timeout: const Duration(seconds: 3),
        delay: (duration) async => delays.add(duration),
      );

      await expectLater(
        poller.pollUntilComplete('job-1'),
        throwsA(isA<AnalysisPollingTimeoutException>()),
      );
      expect(client.statusRequests.length, 3);
      expect(delays, List.filled(3, const Duration(seconds: 1)));
      expect(client.resultRequests, isEmpty);
    },
  );

  test(
    'cancellation stops local polling without a backend cancel request',
    () async {
      final client = FakeAnalysisApiClient(
        statuses: {
          'job-1': [job('job-1', AnalysisJobStatus.processing)],
        },
        results: {},
      );
      final cancellation = AnalysisPollingCancellationToken();
      final poller = AnalysisJobPoller(
        client: client,
        delay: (_) async => cancellation.cancel(),
      );

      await expectLater(
        poller.pollUntilComplete('job-1', cancellation: cancellation),
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(client.statusRequests, ['job-1']);
      expect(client.resultRequests, isEmpty);
    },
  );

  test('independent jobs cannot cross status or result data', () async {
    final client = FakeAnalysisApiClient(
      statuses: {
        'job-a': [job('job-a', AnalysisJobStatus.completed)],
        'job-b': [job('job-b', AnalysisJobStatus.completed)],
      },
      results: {'job-a': timeline('C'), 'job-b': timeline('G')},
    );
    final poller = AnalysisJobPoller(client: client, delay: (_) async {});

    final completions = await Future.wait([
      poller.pollUntilComplete('job-a'),
      poller.pollUntilComplete('job-b'),
    ]);

    expect(completions[0].job.jobId, 'job-a');
    expect(completions[0].timeline.bars.single.beats.single.chord, 'C');
    expect(completions[1].job.jobId, 'job-b');
    expect(completions[1].timeline.bars.single.beats.single.chord, 'G');
    expect(client.resultRequests, containsAll(['job-a', 'job-b']));
  });

  test('a job cancelled on the server stops polling as cancelled', () async {
    final client = FakeAnalysisApiClient(
      statuses: {
        'job-1': [
          job('job-1', AnalysisJobStatus.processing),
          job('job-1', AnalysisJobStatus.cancelled),
        ],
      },
      results: {},
    );
    final poller = AnalysisJobPoller(client: client, delay: (_) async {});

    await expectLater(
      poller.pollUntilComplete('job-1'),
      throwsA(isA<AnalysisPollingCancelledException>()),
    );
    expect(client.resultRequests, isEmpty);
  });

  group('resilience', () {
    FakeAnalysisApiClient completedClient() => FakeAnalysisApiClient(
      statuses: {
        'job-1': [job('job-1', AnalysisJobStatus.completed)],
      },
      results: {'job-1': timeline('C')},
    );

    AnalysisJobPoller pollerFor(
      FakeAnalysisApiClient client,
      List<Duration> delays, {
      int maxTransientRetries = 5,
      Duration timeout = const Duration(minutes: 10),
    }) => AnalysisJobPoller(
      client: client,
      pollingInterval: const Duration(seconds: 1),
      timeout: timeout,
      maxTransientRetries: maxTransientRetries,
      retryBackoff: const Duration(seconds: 2),
      maxRetryBackoff: const Duration(seconds: 5),
      delay: (duration) async => delays.add(duration),
    );

    test('retries 429 and 503 status polls with capped backoff', () async {
      final client = completedClient()
        ..jobErrors.addAll([
          apiError(429, 'rate_limited'),
          apiError(503, 'service_unavailable'),
          apiError(503, 'service_unavailable'),
        ]);
      final delays = <Duration>[];

      final result = await pollerFor(client, delays).pollUntilComplete('job-1');

      expect(result.job.status, AnalysisJobStatus.completed);
      expect(client.statusRequests.length, 4);
      expect(delays, [
        const Duration(seconds: 2),
        const Duration(seconds: 4),
        const Duration(seconds: 5),
      ]);
    });

    test('gives up after the retry budget and surfaces the error', () async {
      final client = completedClient()
        ..jobErrors.addAll(
          List.filled(10, apiError(503, 'service_unavailable')),
        );
      final delays = <Duration>[];

      await expectLater(
        pollerFor(
          client,
          delays,
          maxTransientRetries: 2,
        ).pollUntilComplete('job-1'),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.statusCode,
            'status',
            503,
          ),
        ),
      );
      expect(client.statusRequests.length, 3);
      expect(delays.length, 2);
    });

    test('a successful poll resets the retry budget', () async {
      final client = FakeAnalysisApiClient(
        statuses: {
          'job-1': [
            job('job-1', AnalysisJobStatus.processing),
            job('job-1', AnalysisJobStatus.completed),
          ],
        },
        results: {'job-1': timeline('C')},
      )..jobErrors.add(apiError(429, 'rate_limited'));
      final delays = <Duration>[];

      await pollerFor(
        client,
        delays,
        maxTransientRetries: 1,
      ).pollUntilComplete('job-1');

      expect(client.statusRequests.length, 3);
    });

    test('does not retry permanent errors', () async {
      for (final error in [
        apiError(401, 'authentication_required'),
        apiError(404, 'job_not_found'),
        apiError(500, 'unexpected_api_error'),
      ]) {
        final client = completedClient()..jobErrors.add(error);
        final delays = <Duration>[];

        await expectLater(
          pollerFor(client, delays).pollUntilComplete('job-1'),
          throwsA(isA<AnalysisApiException>()),
        );
        expect(client.statusRequests.length, 1);
        expect(delays, isEmpty);
      }
    });

    test('result_not_ready is retried instead of failing', () async {
      final client = completedClient()
        ..resultErrors.addAll([
          apiError(409, 'result_not_ready'),
          apiError(409, 'result_not_ready'),
        ]);
      final delays = <Duration>[];

      final result = await pollerFor(client, delays).pollUntilComplete('job-1');

      expect(result.timeline.bars.single.beats.single.chord, 'C');
      expect(client.resultRequests.length, 3);
      expect(delays, List.filled(2, const Duration(seconds: 1)));
    });

    test('result 429 is retried with backoff', () async {
      final client = completedClient()..resultErrors.add(apiError(429, 'x'));
      final delays = <Duration>[];

      await pollerFor(client, delays).pollUntilComplete('job-1');

      expect(client.resultRequests.length, 2);
      expect(delays, [const Duration(seconds: 2)]);
    });

    test('a result that never becomes ready ends in a timeout', () async {
      final client = completedClient()
        ..resultErrors.addAll(
          List.filled(20, apiError(409, 'result_not_ready')),
        );
      final delays = <Duration>[];

      await expectLater(
        pollerFor(
          client,
          delays,
          maxTransientRetries: 100,
          timeout: const Duration(seconds: 3),
        ).pollUntilComplete('job-1'),
        throwsA(isA<AnalysisPollingTimeoutException>()),
      );
    });

    test('cancelling during a retry wait stops polling', () async {
      final client = completedClient()
        ..jobErrors.addAll(List.filled(5, apiError(503, 'x')));
      final cancellation = AnalysisPollingCancellationToken();
      final poller = AnalysisJobPoller(
        client: client,
        delay: (_) async => cancellation.cancel(),
      );

      await expectLater(
        poller.pollUntilComplete('job-1', cancellation: cancellation),
        throwsA(isA<AnalysisPollingCancelledException>()),
      );
      expect(client.statusRequests.length, 1);
    });
  });
}
