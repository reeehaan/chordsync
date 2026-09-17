import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:chordsync/features/analysis/data/analysis_api_client.dart';
import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

const completedJobJson = {
  'job_id': 'job-123',
  'status': 'completed',
  'created_at': '2026-09-15T08:30:00Z',
  'updated_at': '2026-09-15T08:31:00Z',
  'error': null,
  'result_available': true,
};

const timelineJson = {
  'schema_version': 1,
  'bpm': 120.0,
  'beats_per_bar': 4,
  'beat_source': 'synthetic-madmom',
  'lyric_source': 'synthetic-whisperx',
  'bars': [
    {
      'bar_number': 1,
      'start_time': 0.0,
      'end_time': 1.0,
      'beats': [
        {'time': 0.0, 'beat_number': 1, 'is_downbeat': true, 'chord': 'C'},
      ],
    },
  ],
  'lyrics': [
    {
      'start': 0.1,
      'end': 0.5,
      'text': 'steady',
      'words': [
        {'start': 0.1, 'end': 0.5, 'text': 'steady'},
      ],
    },
  ],
};

typedef ResponseHandler =
    FutureOr<ResponseBody> Function(RequestOptions options);

class FakeHttpClientAdapter implements HttpClientAdapter {
  FakeHttpClientAdapter(this.handler);

  final ResponseHandler handler;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (requestStream != null) await requestStream.drain<void>();
    return handler(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody jsonResponse(Object payload, int statusCode) {
  return ResponseBody.fromString(
    jsonEncode(payload),
    statusCode,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    },
  );
}

DioAnalysisApiClient clientWith(FakeHttpClientAdapter adapter) {
  final dio = Dio(BaseOptions(baseUrl: 'http://test.invalid'));
  dio.httpClientAdapter = adapter;
  return DioAnalysisApiClient(baseUrl: 'http://test.invalid', dio: dio);
}

void main() {
  late Directory temporaryDirectory;
  late File audioFile;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'chordsync-api-',
    );
    audioFile = File('${temporaryDirectory.path}/synthetic.wav');
    await audioFile.writeAsBytes([82, 73, 70, 70, 1, 2, 3]);
  });

  tearDown(() async {
    await temporaryDirectory.delete(recursive: true);
  });

  test(
    'creates a job with exact file-backed multipart contract and progress',
    () async {
      late FormData sentForm;
      final adapter = FakeHttpClientAdapter((options) {
        sentForm = options.data as FormData;
        return jsonResponse({...completedJobJson, 'status': 'queued'}, 202);
      });
      final progress = <(int, int)>[];

      final job = await clientWith(adapter).createJob(
        title: 'Synthetic upload',
        audioFile: audioFile,
        onSendProgress: (sent, total) => progress.add((sent, total)),
      );

      final request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.uri.path, '/analysis/jobs');
      expect(sentForm.fields.single.key, 'title');
      expect(sentForm.fields.single.value, 'Synthetic upload');
      expect(sentForm.files.single.key, 'audio');
      expect(sentForm.files.single.value.filename, 'synthetic.wav');
      expect(sentForm.files.single.value.length, await audioFile.length());
      expect(progress, isNotEmpty);
      expect(progress.last.$1, progress.last.$2);
      expect(job.jobId, 'job-123');
      expect(job.status, AnalysisJobStatus.queued);
    },
  );

  test('gets status from the correct path', () async {
    final adapter = FakeHttpClientAdapter(
      (options) => jsonResponse(completedJobJson, 200),
    );

    final job = await clientWith(adapter).getJob('job-123');

    expect(adapter.requests.single.uri.path, '/analysis/jobs/job-123');
    expect(adapter.requests.single.method, 'GET');
    expect(job.status, AnalysisJobStatus.completed);
  });

  test(
    'parses completed result with the existing SharedTimeline model',
    () async {
      final adapter = FakeHttpClientAdapter(
        (options) => jsonResponse(timelineJson, 200),
      );

      final timeline = await clientWith(adapter).getResult('job-123');

      expect(adapter.requests.single.uri.path, '/analysis/jobs/job-123/result');
      expect(timeline.schemaVersion, 1);
      expect(timeline.bpm, 120.0);
      expect(timeline.beatsPerBar, 4);
      expect(timeline.bars.single.beats.single.chord, 'C');
      expect(timeline.totalBeatCount, 1);
      expect(timeline.totalLyricWordCount, 1);
    },
  );

  for (final testCase in [
    (404, 'job_not_found'),
    (409, 'result_not_ready'),
    (409, 'analysis_failed'),
    (400, 'empty_audio'),
    (415, 'unsupported_audio_format'),
    (413, 'audio_too_large'),
    (500, 'audio_storage_failed'),
  ]) {
    test('translates backend ${testCase.$2} error', () async {
      final adapter = FakeHttpClientAdapter(
        (options) => jsonResponse({
          'error': {'code': testCase.$2, 'message': 'Safe message.'},
        }, testCase.$1),
      );

      final future = clientWith(adapter).getJob('job-123');

      await expectLater(
        future,
        throwsA(
          isA<AnalysisApiException>()
              .having((error) => error.statusCode, 'statusCode', testCase.$1)
              .having((error) => error.code, 'code', testCase.$2)
              .having((error) => error.message, 'message', 'Safe message.'),
        ),
      );
    });
  }

  test('handles backend 422 validation response safely', () async {
    final adapter = FakeHttpClientAdapter(
      (options) => jsonResponse({
        'detail': [
          {'msg': 'Field required'},
        ],
      }, 422),
    );

    await expectLater(
      clientWith(adapter).getJob('job-123'),
      throwsA(
        isA<AnalysisApiException>()
            .having((error) => error.statusCode, 'statusCode', 422)
            .having((error) => error.code, 'code', 'request_validation_failed'),
      ),
    );
  });

  test(
    'distinguishes transport failures without leaking Dio exceptions',
    () async {
      final adapter = FakeHttpClientAdapter((options) {
        throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
          message: 'private socket detail',
        );
      });

      final future = clientWith(adapter).getJob('job-123');

      await expectLater(
        future,
        throwsA(
          isA<AnalysisTransportException>().having(
            (error) => error.toString(),
            'safe output',
            isNot(contains('DioException')),
          ),
        ),
      );
    },
  );

  test('turns malformed successful responses into data exceptions', () async {
    final adapter = FakeHttpClientAdapter(
      (options) => jsonResponse(['not', 'a', 'job'], 200),
    );

    await expectLater(
      clientWith(adapter).getJob('job-123'),
      throwsA(isA<AnalysisDataException>()),
    );
  });

  test('turns syntactically malformed JSON into a data exception', () async {
    final adapter = FakeHttpClientAdapter(
      (options) => ResponseBody.fromString(
        '{not-json',
        200,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      ),
    );

    await expectLater(
      clientWith(adapter).getJob('job-123'),
      throwsA(isA<AnalysisDataException>()),
    );
  });
}
