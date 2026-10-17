import 'analysis_client_errors.dart';

/// Job states reported by the backend. `awaitingUpload` and `validating` only
/// occur with the hosted presigned-upload flow.
enum AnalysisJobStatus {
  awaitingUpload,
  validating,
  queued,
  processing,
  completed,
  failed;

  static AnalysisJobStatus fromJson(String value) {
    return switch (value) {
      'awaiting_upload' => awaitingUpload,
      'validating' => validating,
      'queued' => queued,
      'processing' => processing,
      'completed' => completed,
      'failed' => failed,
      _ => throw AnalysisDataException('Unknown analysis job status: $value'),
    };
  }
}

class AnalysisJobError {
  const AnalysisJobError({required this.code, required this.message});

  factory AnalysisJobError.fromJson(Map<String, dynamic> json) {
    try {
      return AnalysisJobError(
        code: json['code'] as String,
        message: json['message'] as String,
      );
    } on Object {
      throw const AnalysisDataException('Malformed analysis job error.');
    }
  }

  final String code;
  final String message;
}

class AnalysisJob {
  const AnalysisJob({
    required this.jobId,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    required this.error,
    required this.resultAvailable,
  });

  factory AnalysisJob.fromJson(Map<String, dynamic> json) {
    try {
      final rawError = json['error'];
      return AnalysisJob(
        jobId: json['job_id'] as String,
        status: AnalysisJobStatus.fromJson(json['status'] as String),
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
        error: rawError == null
            ? null
            : AnalysisJobError.fromJson(rawError as Map<String, dynamic>),
        resultAvailable: json['result_available'] as bool,
      );
    } on AnalysisDataException {
      rethrow;
    } on Object {
      throw const AnalysisDataException('Malformed analysis job response.');
    }
  }

  final String jobId;
  final AnalysisJobStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final AnalysisJobError? error;
  final bool resultAvailable;
}
