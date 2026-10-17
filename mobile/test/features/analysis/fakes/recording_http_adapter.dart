import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

typedef RecordedHandler = FutureOr<ResponseBody> Function(RecordedRequest);

class RecordedRequest {
  RecordedRequest(this.options, this.body);

  final RequestOptions options;

  /// Raw bytes that were sent as the request body.
  final List<int> body;

  String get method => options.method;
  Uri get uri => options.uri;
  Map<String, dynamic> get headers => options.headers;
}

/// A fake HTTP adapter that records each request, including its body bytes.
class RecordingHttpAdapter implements HttpClientAdapter {
  RecordingHttpAdapter(this.handler);

  final RecordedHandler handler;
  final requests = <RecordedRequest>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final bytes = <int>[];
    if (requestStream != null) {
      await for (final chunk in requestStream) {
        bytes.addAll(chunk);
      }
    }
    final request = RecordedRequest(options, bytes);
    requests.add(request);
    return handler(request);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody jsonBody(Object payload, int statusCode) =>
    ResponseBody.fromString(
      jsonEncode(payload),
      statusCode,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );

ResponseBody xmlBody(String xml, int statusCode) => ResponseBody.fromString(
  xml,
  statusCode,
  headers: {
    Headers.contentTypeHeader: ['application/xml'],
  },
);

Dio dioWith(RecordingHttpAdapter adapter, {String baseUrl = ''}) {
  final dio = Dio(BaseOptions(baseUrl: baseUrl));
  dio.httpClientAdapter = adapter;
  return dio;
}

const hostedTimelineJson = {
  'schema_version': 1,
  'bpm': 90.0,
  'beats_per_bar': 4,
  'beat_source': 'madmom',
  'lyric_source': 'whisperx-small',
  'bars': [
    {
      'bar_number': 1,
      'start_time': 0.0,
      'end_time': 2.0,
      'beats': [
        {'time': 0.0, 'beat_number': 1, 'is_downbeat': true, 'chord': 'C'},
      ],
    },
  ],
  'lyrics': [
    {
      'start': 0.1,
      'end': 0.5,
      'text': 'hello',
      'words': [
        {'start': 0.1, 'end': 0.5, 'text': 'hello'},
      ],
    },
  ],
};

Map<String, Object?> hostedJobJson(String status, {String id = 'job-1'}) => {
  'job_id': id,
  'status': status,
  'created_at': '2026-10-16T10:57:36.942953Z',
  'updated_at': '2026-10-16T10:58:15.255605Z',
  'error': null,
  'result_available': status == 'completed',
};

Map<String, Object?> uploadTargetJson({
  String id = 'job-1',
  String url =
      'https://bucket.s3.ap-southeast-1.amazonaws.com/jobs/job-1/source/input.wav?X-Amz-Signature=abc&X-Amz-Expires=600',
  String method = 'PUT',
  String expiresAt = '2099-01-01T00:00:00Z',
  Map<String, String>? headers,
}) => {
  'job_id': id,
  'status': 'awaiting_upload',
  'upload_url': url,
  'upload_method': method,
  'required_headers':
      headers ??
      {
        'Content-Type': 'audio/wav',
        'Content-Length': '7',
        'x-amz-server-side-encryption': 'AES256',
        'x-amz-tagging': 'chordsync-upload=presigned',
      },
  'expires_at': expiresAt,
  'source_object_key': 'jobs/$id/source/input.wav',
};
