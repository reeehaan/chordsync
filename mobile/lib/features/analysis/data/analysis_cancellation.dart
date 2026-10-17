/// A flag the UI sets to stop an analysis in progress (upload or polling).
class AnalysisPollingCancellationToken {
  bool _isCancelled = false;

  bool get isCancelled => _isCancelled;

  void cancel() => _isCancelled = true;
}
