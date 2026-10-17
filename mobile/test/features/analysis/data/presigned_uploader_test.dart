import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/hosted_upload_models.dart';
import 'package:chordsync/features/analysis/data/presigned_uploader.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/recording_http_adapter.dart';

const _audio = [82, 73, 70, 70, 1, 2, 3];

UploadTarget _target({
  String expiresAt = '2099-01-01T00:00:00Z',
  Map<String, String>? headers,
}) => UploadTarget.fromJson(
  uploadTargetJson(expiresAt: expiresAt, headers: headers),
);

ResponseBody _ok() => ResponseBody.fromString(
  '',
  200,
  headers: {
    'etag': ['"abc"'],
  },
);

void main() {
  late Directory directory;
  late File file;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('chordsync-upload-');
    file = File('${directory.path}/song.wav');
    await file.writeAsBytes(_audio);
  });

  tearDown(() => directory.delete(recursive: true));

  group('request', () {
    test(
      'sends the exact bytes with only the signed headers, as a PUT',
      () async {
        final adapter = RecordingHttpAdapter((_) => _ok());
        final target = _target();

        await DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: target, file: file);

        final sent = adapter.requests.single;
        expect(sent.method, 'PUT');
        expect(sent.body, _audio);
        expect(sent.headers['Content-Type'], 'audio/wav');
        expect(sent.headers['Content-Length'], '7');
        expect(sent.headers['x-amz-server-side-encryption'], 'AES256');
        expect(sent.headers['x-amz-tagging'], 'chordsync-upload=presigned');
      },
    );

    test(
      'never attaches the ChordSync bearer token or any credential',
      () async {
        final adapter = RecordingHttpAdapter((_) => _ok());
        await DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: _target(), file: file);

        final names = adapter.requests.single.headers.keys.map(
          (k) => k.toLowerCase(),
        );
        expect(names, isNot(contains('authorization')));
        expect(names, isNot(contains('cookie')));
        expect(names, isNot(contains('x-api-key')));
      },
    );

    test('leaves the signed URL exactly as issued', () async {
      final adapter = RecordingHttpAdapter((_) => _ok());
      final target = _target();

      await DioPresignedUploader(
        dio: dioWith(adapter),
      ).upload(target: target, file: file);

      expect(adapter.requests.single.uri, target.uploadUrl);
      expect(
        adapter.requests.single.uri.query,
        'X-Amz-Signature=abc&X-Amz-Expires=600',
      );
      expect(adapter.requests.single.options.baseUrl, isEmpty);
    });

    test('reports upload progress', () async {
      final adapter = RecordingHttpAdapter((_) => _ok());
      final progress = <(int, int)>[];
      await DioPresignedUploader(dio: dioWith(adapter)).upload(
        target: _target(),
        file: file,
        onProgress: (sent, total) => progress.add((sent, total)),
      );
      expect(progress, isNotEmpty);
    });

    test(
      'refuses to send a file whose size no longer matches the signature',
      () async {
        final adapter = RecordingHttpAdapter((_) => _ok());
        await file.writeAsBytes([
          ..._audio,
          9,
          9,
        ]); // grew after the job was created

        await expectLater(
          DioPresignedUploader(
            dio: dioWith(adapter),
          ).upload(target: _target(), file: file),
          throwsA(
            isA<AnalysisUploadException>().having(
              (e) => e.failure,
              'failure',
              AnalysisUploadFailure.rejected,
            ),
          ),
        );
        expect(adapter.requests, isEmpty);
      },
    );
  });

  group('failures', () {
    test(
      'an already expired link is reported without sending anything',
      () async {
        final adapter = RecordingHttpAdapter((_) => _ok());
        await expectLater(
          DioPresignedUploader(dio: dioWith(adapter)).upload(
            target: _target(expiresAt: '2020-01-01T00:00:00Z'),
            file: file,
          ),
          throwsA(
            isA<AnalysisUploadException>().having(
              (e) => e.failure,
              'failure',
              AnalysisUploadFailure.urlExpired,
            ),
          ),
        );
        expect(adapter.requests, isEmpty);
      },
    );

    test('storage saying the request expired is urlExpired', () async {
      final adapter = RecordingHttpAdapter(
        (_) => xmlBody(
          '<Error><Code>AccessDenied</Code><Message>Request has expired</Message></Error>',
          403,
        ),
      );
      await expectLater(
        DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: _target(), file: file),
        throwsA(
          isA<AnalysisUploadException>().having(
            (e) => e.failure,
            'failure',
            AnalysisUploadFailure.urlExpired,
          ),
        ),
      );
    });

    test('a link that expires during the upload is urlExpired', () async {
      var now = DateTime.utc(2026, 1, 1);
      final adapter = RecordingHttpAdapter((_) {
        now = DateTime.utc(2026, 1, 1, 1);
        return xmlBody('<Error><Code>AccessDenied</Code></Error>', 403);
      });
      await expectLater(
        DioPresignedUploader(dio: dioWith(adapter), clock: () => now).upload(
          target: _target(expiresAt: '2026-01-01T00:10:00Z'),
          file: file,
        ),
        throwsA(
          isA<AnalysisUploadException>().having(
            (e) => e.failure,
            'failure',
            AnalysisUploadFailure.urlExpired,
          ),
        ),
      );
    });

    test(
      'signature or header problems are rejected, not retried as expiry',
      () async {
        final adapter = RecordingHttpAdapter(
          (_) =>
              xmlBody('<Error><Code>SignatureDoesNotMatch</Code></Error>', 403),
        );
        await expectLater(
          DioPresignedUploader(
            dio: dioWith(adapter),
          ).upload(target: _target(), file: file),
          throwsA(
            isA<AnalysisUploadException>()
                .having(
                  (e) => e.failure,
                  'failure',
                  AnalysisUploadFailure.rejected,
                )
                .having((e) => e.message, 'message', contains('403')),
          ),
        );
      },
    );

    test('other non-2xx responses are rejected', () async {
      for (final status in [400, 500, 503]) {
        final adapter = RecordingHttpAdapter(
          (_) => xmlBody('<Error/>', status),
        );
        await expectLater(
          DioPresignedUploader(
            dio: dioWith(adapter),
          ).upload(target: _target(), file: file),
          throwsA(
            isA<AnalysisUploadException>().having(
              (e) => e.failure,
              'failure',
              AnalysisUploadFailure.rejected,
            ),
          ),
        );
      }
    });

    test('connection failures and timeouts are distinct', () async {
      var adapter = RecordingHttpAdapter(
        (r) => throw DioException.connectionError(
          requestOptions: r.options,
          reason: 'down',
        ),
      );
      await expectLater(
        DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: _target(), file: file),
        throwsA(
          isA<AnalysisUploadException>().having(
            (e) => e.failure,
            'failure',
            AnalysisUploadFailure.connection,
          ),
        ),
      );
      adapter = RecordingHttpAdapter(
        (r) => throw DioException.sendTimeout(
          timeout: const Duration(seconds: 1),
          requestOptions: r.options,
        ),
      );
      await expectLater(
        DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: _target(), file: file),
        throwsA(
          isA<AnalysisUploadException>().having(
            (e) => e.failure,
            'failure',
            AnalysisUploadFailure.timeout,
          ),
        ),
      );
    });

    test(
      'cancelling stops the upload with the existing cancelled exception',
      () async {
        final started = Completer<void>();
        final adapter = RecordingHttpAdapter((r) async {
          started.complete();
          await Completer<void>()
              .future; // the real adapter would abort on cancel
          return _ok();
        });
        final token = CancelToken();
        final result = DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: _target(), file: file, cancelToken: token);
        // Dio races the request against the token; cancel once the request began.
        unawaited(started.future.then((_) => token.cancel()));
        await expectLater(
          result,
          throwsA(isA<AnalysisPollingCancelledException>()),
        );
      },
    );

    test('error messages never contain the presigned URL', () async {
      final adapter = RecordingHttpAdapter((_) => xmlBody('<Error/>', 500));
      try {
        await DioPresignedUploader(
          dio: dioWith(adapter),
        ).upload(target: _target(), file: file);
        fail('expected a failure');
      } on AnalysisUploadException catch (error) {
        expect(error.toString(), isNot(contains('X-Amz')));
        expect(error.toString(), isNot(contains('amazonaws')));
      }
    });
  });
}
