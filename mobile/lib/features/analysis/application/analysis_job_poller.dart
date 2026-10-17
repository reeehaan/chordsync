import '../../practice_timeline/data/shared_timeline.dart';
import '../data/analysis_api_client.dart';
import '../data/analysis_cancellation.dart';
import '../data/analysis_client_errors.dart';
import '../data/analysis_job.dart';

export '../data/analysis_cancellation.dart';

typedef AnalysisPollingDelay = Future<void> Function(Duration duration);
typedef AnalysisJobUpdate = void Function(AnalysisJob job);

class AnalysisCompletedResult {
  const AnalysisCompletedResult({required this.job, required this.timeline});

  final AnalysisJob job;
  final SharedTimeline timeline;
}

abstract interface class AnalysisJobPolling {
  Future<AnalysisCompletedResult> pollUntilComplete(
    String jobId, {
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  });
}

class AnalysisJobPoller implements AnalysisJobPolling {
  factory AnalysisJobPoller({
    required AnalysisApiClient client,
    Duration pollingInterval = const Duration(seconds: 1),
    Duration timeout = const Duration(minutes: 15),
    AnalysisPollingDelay delay = Future<void>.delayed,
  }) {
    if (pollingInterval <= Duration.zero) {
      throw ArgumentError.value(pollingInterval, 'pollingInterval');
    }
    if (timeout <= Duration.zero) {
      throw ArgumentError.value(timeout, 'timeout');
    }
    return AnalysisJobPoller._(
      client: client,
      pollingInterval: pollingInterval,
      timeout: timeout,
      delay: delay,
    );
  }

  AnalysisJobPoller._({
    required this._client,
    required this._pollingInterval,
    required this._timeout,
    required this._delay,
  });

  final AnalysisApiClient _client;
  final Duration _pollingInterval;
  final Duration _timeout;
  final AnalysisPollingDelay _delay;

  @override
  Future<AnalysisCompletedResult> pollUntilComplete(
    String jobId, {
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  }) async {
    var elapsedPollingDelay = Duration.zero;

    while (true) {
      if (cancellation?.isCancelled ?? false) {
        throw const AnalysisPollingCancelledException();
      }
      if (elapsedPollingDelay >= _timeout) {
        throw const AnalysisPollingTimeoutException();
      }

      final job = await _client.getJob(jobId);
      onJobUpdated?.call(job);
      switch (job.status) {
        case AnalysisJobStatus.completed:
          final timeline = await _client.getResult(jobId);
          return AnalysisCompletedResult(job: job, timeline: timeline);
        case AnalysisJobStatus.failed:
          final error = job.error;
          throw AnalysisApiException(
            statusCode: 409,
            code: error?.code ?? 'analysis_failed',
            message: error?.message ?? 'Analysis could not be completed.',
          );
        case AnalysisJobStatus.awaitingUpload:
        case AnalysisJobStatus.validating:
        case AnalysisJobStatus.queued:
        case AnalysisJobStatus.processing:
          final remaining = _timeout - elapsedPollingDelay;
          final nextDelay = remaining < _pollingInterval
              ? remaining
              : _pollingInterval;
          await _delay(nextDelay);
          elapsedPollingDelay += nextDelay;
      }
    }
  }
}
