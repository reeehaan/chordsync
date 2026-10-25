import 'dart:io';
import 'dart:typed_data';

import 'package:chordsync/features/analysis/application/cloud_library_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

class _Adapter implements HttpClientAdapter {
  _Adapter(this.declaredBytes);

  final int declaredBytes;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async => ResponseBody(
    Stream.value(Uint8List(2048)),
    200,
    headers: {
      Headers.contentLengthHeader: ['$declaredBytes'],
    },
  );

  @override
  void close({bool force = false}) {}
}

void main() {
  late Directory directory;

  setUp(() => directory = Directory.systemTemp.createTempSync('cap-test-'));
  tearDown(() => directory.deleteSync(recursive: true));

  test('a download that says it is bigger than a song is stopped', () async {
    final downloader = DioAudioDownloader(
      Dio()..httpClientAdapter = _Adapter(DioAudioDownloader.maxBytes + 1),
    );

    await expectLater(
      downloader.download(
        'https://bucket.invalid/a.mp3',
        '${directory.path}/a',
      ),
      throwsA(
        isA<DioException>().having(
          (error) => error.type,
          'type',
          DioExceptionType.cancel,
        ),
      ),
    );
  });

  test('a normal song-sized download goes through', () async {
    final downloader = DioAudioDownloader(
      Dio()..httpClientAdapter = _Adapter(2048),
    );

    await downloader.download(
      'https://bucket.invalid/a.mp3',
      '${directory.path}/a',
    );

    expect(File('${directory.path}/a').lengthSync(), 2048);
  });
}
