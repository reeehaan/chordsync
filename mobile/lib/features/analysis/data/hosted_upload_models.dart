import 'analysis_client_errors.dart';
import 'analysis_job.dart';

const maxAnalysisUploadBytes = 25 * 1024 * 1024;

/// Body of `POST /analysis/jobs` (hosted). Metadata only, never audio.
class CreateUploadRequest {
  const CreateUploadRequest({
    required this.title,
    required this.filename,
    required this.declaredSizeBytes,
    this.contentType,
  });

  final String title;
  final String filename;
  final int declaredSizeBytes;
  final String? contentType;

  Map<String, Object?> toJson() => {
    'title': title,
    'filename': filename,
    'declared_size_bytes': declaredSizeBytes,
    if (contentType != null) 'content_type': contentType,
  };
}

/// Response of `POST /analysis/jobs` (hosted): where and how to upload.
class UploadTarget {
  const UploadTarget({
    required this.jobId,
    required this.status,
    required this.uploadUrl,
    required this.requiredHeaders,
    required this.expiresAt,
    required this.sourceObjectKey,
  });

  factory UploadTarget.fromJson(Map<String, dynamic> json) {
    try {
      final method = json['upload_method'] as String;
      final url = Uri.parse(json['upload_url'] as String);
      // Audio must never travel over plain HTTP, and the URL is a PUT target.
      if (method != 'PUT' || url.scheme != 'https' || url.host.isEmpty) {
        throw const AnalysisDataException('Unusable upload target.');
      }
      final headers = (json['required_headers'] as Map).map(
        (key, value) => MapEntry(key as String, value as String),
      );
      return UploadTarget(
        jobId: json['job_id'] as String,
        status: AnalysisJobStatus.fromJson(json['status'] as String),
        uploadUrl: url,
        requiredHeaders: Map.unmodifiable(headers),
        expiresAt: DateTime.parse(json['expires_at'] as String),
        sourceObjectKey: json['source_object_key'] as String,
      );
    } on AnalysisDataException {
      rethrow;
    } on Object {
      throw const AnalysisDataException('Malformed upload target response.');
    }
  }

  final String jobId;
  final AnalysisJobStatus status;

  /// Sensitive: it carries a signature. Never log it.
  final Uri uploadUrl;

  /// Headers that must be sent exactly as given (they are signed).
  final Map<String, String> requiredHeaders;
  final DateTime expiresAt;
  final String sourceObjectKey;

  @override
  String toString() => 'UploadTarget(job: $jobId, expires: $expiresAt)';
}

/// Response of `POST /analysis/jobs/{id}/confirm-upload`.
class ConfirmOutcome {
  const ConfirmOutcome({required this.job, required this.newlyQueued});

  final AnalysisJob job;

  /// True for 202 (this call queued the job), false for 200 (a repeat call).
  final bool newlyQueued;
}
