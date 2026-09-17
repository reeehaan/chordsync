class AnalysisDataException implements Exception {
  const AnalysisDataException(this.message);

  final String message;

  @override
  String toString() => 'AnalysisDataException: $message';
}

class AnalysisApiException implements Exception {
  const AnalysisApiException({
    required this.statusCode,
    required this.code,
    required this.message,
  });

  final int statusCode;
  final String code;
  final String message;

  @override
  String toString() => 'AnalysisApiException($statusCode, $code): $message';
}

class AnalysisTransportException implements Exception {
  const AnalysisTransportException(this.message);

  final String message;

  @override
  String toString() => 'AnalysisTransportException: $message';
}

class AnalysisPollingTimeoutException implements Exception {
  const AnalysisPollingTimeoutException();

  @override
  String toString() => 'Analysis polling timed out.';
}

class AnalysisPollingCancelledException implements Exception {
  const AnalysisPollingCancelledException();

  @override
  String toString() => 'Analysis polling was cancelled.';
}
