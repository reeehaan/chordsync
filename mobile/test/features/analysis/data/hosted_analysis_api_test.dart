import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/hosted_analysis_api.dart';
import 'package:chordsync/features/analysis/data/hosted_upload_models.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/recording_http_adapter.dart';

const _token = 'test-token-0123456789abcdefghijklmnop';
const _unauthorized = {
  'error': {'code': 'unauthorized', 'message': 'Authentication required.'},
};
const _notFound = {
  'error': {'code': 'job_not_found', 'message': 'Analysis job was not found.'},
};

DioHostedAnalysisApi apiWith(
  RecordingHttpAdapter adapter, {
  String? token = _token,
}) => DioHostedAnalysisApi(
  baseUrl: 'https://api.test.invalid',
  tokenProvider: () => token,
  dio: dioWith(adapter),
);

const _request = CreateUploadRequest(
  title: 'Song',
  filename: 'song.wav',
  declaredSizeBytes: 7,
  contentType: 'audio/wav',
);

void main() {
  group('createUpload', () {
    test(
      'posts metadata only, with the bearer token, and parses the target',
      () async {
        final adapter = RecordingHttpAdapter(
          (_) => jsonBody(uploadTargetJson(), 201),
        );

        final target = await apiWith(adapter).createUpload(_request);

        final sent = adapter.requests.single;
        expect(sent.method, 'POST');
        expect(sent.uri.toString(), 'https://api.test.invalid/analysis/jobs');
        expect(sent.headers['Authorization'], 'Bearer $_token');
        expect(sent.options.data, {
          'title': 'Song',
          'filename': 'song.wav',
          'declared_size_bytes': 7,
          'content_type': 'audio/wav',
        });
        expect(target.jobId, 'job-1');
        expect(target.status, AnalysisJobStatus.awaitingUpload);
        expect(target.uploadUrl.scheme, 'https');
        expect(target.uploadUrl.queryParameters['X-Amz-Signature'], 'abc');
        expect(
          target.requiredHeaders['x-amz-tagging'],
          'chordsync-upload=presigned',
        );
        expect(target.expiresAt, DateTime.utc(2099));
        expect(target.sourceObjectKey, 'jobs/job-1/source/input.wav');
      },
    );

    test('the target never prints its signed URL', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(uploadTargetJson(), 201),
      );
      final target = await apiWith(adapter).createUpload(_request);
      expect(target.toString(), isNot(contains('X-Amz-Signature')));
      expect(target.toString(), isNot(contains('amazonaws')));
    });

    test('omits content_type when none is given', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(uploadTargetJson(), 201),
      );
      await apiWith(adapter).createUpload(
        const CreateUploadRequest(
          title: 'S',
          filename: 's.mp3',
          declaredSizeBytes: 1,
        ),
      );
      expect(
        (adapter.requests.single.options.data as Map).containsKey(
          'content_type',
        ),
        isFalse,
      );
    });

    for (final bad in <String, Map<String, Object?>>{
      'http url': uploadTargetJson(url: 'http://bucket.example/x?sig=1'),
      'POST method': uploadTargetJson(method: 'POST'),
      'unknown status': {...uploadTargetJson(), 'status': 'teleporting'},
      'missing key': {...uploadTargetJson()}..remove('source_object_key'),
      'bad expiry': uploadTargetJson(expiresAt: 'tomorrow'),
    }.entries) {
      test('rejects an unusable target: ${bad.key}', () async {
        final adapter = RecordingHttpAdapter((_) => jsonBody(bad.value, 201));
        expect(
          apiWith(adapter).createUpload(_request),
          throwsA(isA<AnalysisDataException>()),
        );
      });
    }

    test('a 200 instead of 201 is unexpected', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(uploadTargetJson(), 200),
      );
      expect(
        apiWith(adapter).createUpload(_request),
        throwsA(isA<AnalysisDataException>()),
      );
    });

    test('maps 401, 400, 413 and 503 error bodies', () async {
      for (final (status, code) in [
        (401, 'unauthorized'),
        (400, 'unsupported_audio_format'),
        (413, 'audio_too_large'),
        (503, 'service_unavailable'),
      ]) {
        final adapter = RecordingHttpAdapter(
          (_) => jsonBody({
            'error': {'code': code, 'message': 'm'},
          }, status),
        );
        await expectLater(
          apiWith(adapter).createUpload(_request),
          throwsA(
            isA<AnalysisApiException>()
                .having((e) => e.statusCode, 'status', status)
                .having((e) => e.code, 'code', code),
          ),
        );
      }
    });

    test('without a token it fails locally and sends nothing', () async {
      for (final token in [null, '', '   ']) {
        final adapter = RecordingHttpAdapter(
          (_) => jsonBody(uploadTargetJson(), 201),
        );
        await expectLater(
          apiWith(adapter, token: token).createUpload(_request),
          throwsA(
            isA<AnalysisApiException>()
                .having((e) => e.isUnauthorized, 'unauthorized', true)
                .having((e) => e.code, 'code', 'authentication_required'),
          ),
        );
        expect(adapter.requests, isEmpty);
      }
    });

    test('a network failure becomes a transport error', () async {
      final adapter = RecordingHttpAdapter(
        (r) => throw DioException.connectionError(
          requestOptions: r.options,
          reason: 'down',
        ),
      );
      expect(
        apiWith(adapter).createUpload(_request),
        throwsA(isA<AnalysisTransportException>()),
      );
    });
  });

  group('cancelJob', () {
    test(
      'posts to the cancel route with the token and parses the job',
      () async {
        final adapter = RecordingHttpAdapter(
          (_) => jsonBody(hostedJobJson('cancelled', id: 'job-1'), 200),
        );

        final job = await apiWith(adapter).cancelJob('job-1');

        final sent = adapter.requests.single;
        expect(sent.method, 'POST');
        expect(
          sent.uri.toString(),
          'https://api.test.invalid/analysis/jobs/job-1/cancel',
        );
        expect(sent.headers['Authorization'], 'Bearer $_token');
        expect(job.status, AnalysisJobStatus.cancelled);
      },
    );

    test('a finished job answers 409 invalid_job_state', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody({
          'error': {
            'code': 'invalid_job_state',
            'message': 'This job can no longer be cancelled.',
          },
        }, 409),
      );

      await expectLater(
        apiWith(adapter).cancelJob('job-1'),
        throwsA(
          isA<AnalysisApiException>()
              .having((e) => e.statusCode, 'status', 409)
              .having((e) => e.code, 'code', 'invalid_job_state'),
        ),
      );
    });

    test('someone else\'s job is a hidden 404', () async {
      final adapter = RecordingHttpAdapter((_) => jsonBody(_notFound, 404));

      await expectLater(
        apiWith(adapter).cancelJob('job-1'),
        throwsA(
          isA<AnalysisApiException>().having((e) => e.isNotFound, 'nf', true),
        ),
      );
    });

    test('without a token it fails locally and sends nothing', () async {
      final adapter = RecordingHttpAdapter((_) => jsonBody({}, 200));

      await expectLater(
        apiWith(adapter, token: null).cancelJob('job-1'),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.isUnauthorized,
            'u',
            true,
          ),
        ),
      );
      expect(adapter.requests, isEmpty);
    });
  });

  group('confirmUpload', () {
    test('202 means this call queued the job', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(hostedJobJson('queued'), 202),
      );
      final outcome = await apiWith(adapter).confirmUpload('job-1');
      expect(outcome.newlyQueued, isTrue);
      expect(outcome.job.status, AnalysisJobStatus.queued);
      expect(
        adapter.requests.single.uri.path,
        '/analysis/jobs/job-1/confirm-upload',
      );
      expect(
        adapter.requests.single.headers['Authorization'],
        'Bearer $_token',
      );
    });

    test('200 is an idempotent repeat', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(hostedJobJson('processing'), 200),
      );
      final outcome = await apiWith(adapter).confirmUpload('job-1');
      expect(outcome.newlyQueued, isFalse);
      expect(outcome.job.status, AnalysisJobStatus.processing);
    });

    test('409 upload_not_received is an API error with that code', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody({
          'error': {
            'code': 'upload_not_received',
            'message': 'The audio has not been uploaded yet.',
          },
        }, 409),
      );
      await expectLater(
        apiWith(adapter).confirmUpload('job-1'),
        throwsA(
          isA<AnalysisApiException>()
              .having((e) => e.statusCode, 'status', 409)
              .having((e) => e.code, 'code', 'upload_not_received'),
        ),
      );
    });

    test('401 and the hidden 404 are distinguishable by status', () async {
      var adapter = RecordingHttpAdapter((_) => jsonBody(_unauthorized, 401));
      await expectLater(
        apiWith(adapter).confirmUpload('job-1'),
        throwsA(
          isA<AnalysisApiException>().having(
            (e) => e.isUnauthorized,
            'u',
            true,
          ),
        ),
      );
      adapter = RecordingHttpAdapter((_) => jsonBody(_notFound, 404));
      await expectLater(
        apiWith(adapter).confirmUpload('job-1'),
        throwsA(
          isA<AnalysisApiException>().having((e) => e.isNotFound, 'nf', true),
        ),
      );
    });

    test('encodes the job id in the path', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(hostedJobJson('queued'), 202),
      );
      await apiWith(adapter).confirmUpload('a/b c');
      expect(
        adapter.requests.single.uri.path,
        '/analysis/jobs/a%2Fb%20c/confirm-upload',
      );
    });
  });

  group('getJob and getResult', () {
    test('every hosted status parses', () async {
      for (final (raw, expected) in [
        ('awaiting_upload', AnalysisJobStatus.awaitingUpload),
        ('validating', AnalysisJobStatus.validating),
        ('queued', AnalysisJobStatus.queued),
        ('processing', AnalysisJobStatus.processing),
        ('completed', AnalysisJobStatus.completed),
        ('failed', AnalysisJobStatus.failed),
      ]) {
        final adapter = RecordingHttpAdapter(
          (_) => jsonBody(hostedJobJson(raw), 200),
        );
        expect((await apiWith(adapter).getJob('job-1')).status, expected);
      }
    });

    test('a failed job carries its error', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody({
          ...hostedJobJson('failed'),
          'error': {
            'code': 'invalid_audio',
            'message': 'Audio could not be decoded.',
          },
        }, 200),
      );
      final job = await apiWith(adapter).getJob('job-1');
      expect(job.error?.code, 'invalid_audio');
    });

    test('fetches and parses the completed result', () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(hostedTimelineJson, 200),
      );
      final timeline = await apiWith(adapter).getResult('job-1');
      expect(timeline.bpm, 90.0);
      expect(adapter.requests.single.uri.path, '/analysis/jobs/job-1/result');
      expect(
        adapter.requests.single.headers['Authorization'],
        'Bearer $_token',
      );
    });

    test(
      'result not ready (409), unauthorized (401) and hidden (404) map to API errors',
      () async {
        for (final (status, code, body) in [
          (
            409,
            'result_not_ready',
            {
              'error': {
                'code': 'result_not_ready',
                'message': 'Analysis result is not ready.',
              },
            },
          ),
          (401, 'unauthorized', _unauthorized),
          (404, 'job_not_found', _notFound),
        ]) {
          final adapter = RecordingHttpAdapter((_) => jsonBody(body, status));
          await expectLater(
            apiWith(adapter).getResult('job-1'),
            throwsA(
              isA<AnalysisApiException>()
                  .having((e) => e.statusCode, 'status', status)
                  .having((e) => e.code, 'code', code),
            ),
          );
        }
      },
    );

    test('a malformed body becomes a data error, not a widget crash', () async {
      var adapter = RecordingHttpAdapter((_) => jsonBody({'nope': 1}, 200));
      await expectLater(
        apiWith(adapter).getJob('job-1'),
        throwsA(isA<AnalysisDataException>()),
      );
      adapter = RecordingHttpAdapter((_) => jsonBody({'nope': 1}, 200));
      await expectLater(
        apiWith(adapter).getResult('job-1'),
        throwsA(isA<AnalysisDataException>()),
      );
    });

    test('a changing token is read for every request', () async {
      var token = 'first-token-0123456789abcdef';
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody(hostedJobJson('queued'), 200),
      );
      final api = DioHostedAnalysisApi(
        baseUrl: 'https://api.test.invalid',
        tokenProvider: () => token,
        dio: dioWith(adapter),
      );
      await api.getJob('job-1');
      token = 'second-token-0123456789abcdef';
      await api.getJob('job-1');
      expect(adapter.requests.map((r) => r.headers['Authorization']), [
        'Bearer first-token-0123456789abcdef',
        'Bearer second-token-0123456789abcdef',
      ]);
    });
  });
}
