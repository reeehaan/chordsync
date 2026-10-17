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

  /// Missing, wrong or expired access token.
  bool get isUnauthorized => statusCode == 401;

  /// The job does not exist, or belongs to someone else (the server does not
  /// say which).
  bool get isNotFound => statusCode == 404;

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

enum AnalysisUploadFailure {
  /// The presigned URL passed its expiry time.
  urlExpired,

  /// The upload could not reach the storage service.
  connection,

  /// The upload took too long.
  timeout,

  /// The storage service refused the upload.
  rejected,
}

/// The direct upload of the audio to storage failed.
///
/// The message never contains the presigned URL, which is sensitive.
class AnalysisUploadException implements Exception {
  const AnalysisUploadException(this.failure, this.message);

  final AnalysisUploadFailure failure;
  final String message;

  @override
  String toString() => 'AnalysisUploadException(${failure.name}): $message';
}
