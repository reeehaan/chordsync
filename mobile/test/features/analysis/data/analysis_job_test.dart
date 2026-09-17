import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> jobJson({
  String status = 'queued',
  Map<String, dynamic>? error,
  bool resultAvailable = false,
}) => {
  'job_id': 'job-123',
  'status': status,
  'created_at': '2026-09-15T08:30:00Z',
  'updated_at': '2026-09-15T08:31:00+00:00',
  'error': error,
  'result_available': resultAvailable,
};

void main() {
  test('parses every public lifecycle state exactly', () {
    for (final entry in {
      'queued': AnalysisJobStatus.queued,
      'processing': AnalysisJobStatus.processing,
      'completed': AnalysisJobStatus.completed,
      'failed': AnalysisJobStatus.failed,
    }.entries) {
      final job = AnalysisJob.fromJson(
        jobJson(status: entry.key, resultAvailable: entry.key == 'completed'),
      );

      expect(job.status, entry.value);
    }
  });

  test('parses timestamps and safe failed-job error', () {
    final job = AnalysisJob.fromJson(
      jobJson(
        status: 'failed',
        error: {
          'code': 'future_safe_code',
          'message': 'A safe server message.',
        },
      ),
    );

    expect(job.jobId, 'job-123');
    expect(job.createdAt, DateTime.utc(2026, 9, 15, 8, 30));
    expect(job.updatedAt, DateTime.utc(2026, 9, 15, 8, 31));
    expect(job.error?.code, 'future_safe_code');
    expect(job.error?.message, 'A safe server message.');
    expect(job.resultAvailable, isFalse);
  });

  test('rejects an unknown lifecycle value', () {
    expect(
      () => AnalysisJob.fromJson(jobJson(status: 'mystery')),
      throwsA(isA<AnalysisDataException>()),
    );
  });

  test('rejects malformed required fields', () {
    final malformed = jobJson()..remove('job_id');

    expect(
      () => AnalysisJob.fromJson(malformed),
      throwsA(isA<AnalysisDataException>()),
    );
  });
}
