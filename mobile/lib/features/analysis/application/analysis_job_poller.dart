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
    int maxTransientRetries = 5,
    Duration retryBackoff = const Duration(seconds: 2),
    Duration maxRetryBackoff = const Duration(seconds: 30),
    AnalysisPollingDelay delay = Future<void>.delayed,
  }) {
    if (pollingInterval <= Duration.zero) {
      throw ArgumentError.value(pollingInterval, 'pollingInterval');
    }
    if (timeout <= Duration.zero) {
      throw ArgumentError.value(timeout, 'timeout');
    }
    if (maxTransientRetries < 0) {
      throw ArgumentError.value(maxTransientRetries, 'maxTransientRetries');
    }
    if (retryBackoff <= Duration.zero || maxRetryBackoff < retryBackoff) {
      throw ArgumentError.value(retryBackoff, 'retryBackoff');
    }
    return AnalysisJobPoller._(
      client: client,
      pollingInterval: pollingInterval,
      timeout: timeout,
      maxTransientRetries: maxTransientRetries,
      retryBackoff: retryBackoff,
      maxRetryBackoff: maxRetryBackoff,
      delay: delay,
    );
  }

  AnalysisJobPoller._({
    required this._client,
    required this._pollingInterval,
    required this._timeout,
    required this._maxTransientRetries,
    required this._retryBackoff,
    required this._maxRetryBackoff,
    required this._delay,
  });

  final AnalysisApiClient _client;
  final Duration _pollingInterval;
  final Duration _timeout;
  final int _maxTransientRetries;
  final Duration _retryBackoff;
  final Duration _maxRetryBackoff;
  final AnalysisPollingDelay _delay;

  @override
  Future<AnalysisCompletedResult> pollUntilComplete(
    String jobId, {
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  }) async {
    var elapsed = Duration.zero;
    var transientFailures = 0;

    // Waits are bounded by the overall timeout, so retries cannot run forever.
    Future<void> wait(Duration duration) async {
      final remaining = _timeout - elapsed;
      final next = remaining < duration ? remaining : duration;
      await _delay(next);
      elapsed += next;
    }

    // Backoff doubles per consecutive failure, up to a cap.
    Duration backoff(int failures) {
      final scaled = _retryBackoff * (1 << (failures - 1).clamp(0, 16));
      return scaled > _maxRetryBackoff ? _maxRetryBackoff : scaled;
    }

    while (true) {
      if (cancellation?.isCancelled ?? false) {
        throw const AnalysisPollingCancelledException();
      }
      if (elapsed >= _timeout) {
        throw const AnalysisPollingTimeoutException();
      }

      final AnalysisJob job;
      try {
        job = await _client.getJob(jobId);
      } on AnalysisApiException catch (error) {
        if (!_isTransient(error) ||
            ++transientFailures > _maxTransientRetries) {
          rethrow;
        }
        await wait(backoff(transientFailures));
        continue;
      }
      transientFailures = 0;
      onJobUpdated?.call(job);
      switch (job.status) {
        case AnalysisJobStatus.completed:
          try {
            final timeline = await _client.getResult(jobId);
            return AnalysisCompletedResult(job: job, timeline: timeline);
          } on AnalysisApiException catch (error) {
            if (!_isTransient(error) ||
                ++transientFailures > _maxTransientRetries) {
              rethrow;
            }
            // Not ready yet is normal right after completion; check again.
            await wait(
              error.code == 'result_not_ready'
                  ? _pollingInterval
                  : backoff(transientFailures),
            );
          }
        case AnalysisJobStatus.cancelled:
          throw const AnalysisPollingCancelledException();
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
          await wait(_pollingInterval);
      }
    }
  }

  /// Rate limiting, a briefly unavailable service, or a result that is still
  /// being written: all worth another try.
  static bool _isTransient(AnalysisApiException error) =>
      error.statusCode == 429 ||
      error.statusCode == 503 ||
      error.code == 'result_not_ready';
}
