import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';

import 'analysis_client_errors.dart';
import 'hosted_upload_models.dart';

typedef UploadProgress = void Function(int sent, int total);

/// Sends a file to a presigned storage URL.
abstract interface class PresignedUploader {
  Future<void> upload({
    required UploadTarget target,
    required File file,
    UploadProgress? onProgress,
    CancelToken? cancelToken,
  });
}

class DioPresignedUploader implements PresignedUploader {
  /// [dio] must be a plain client: no base URL and no interceptor that adds
  /// the ChordSync bearer token, because storage rejects extra credentials.
  DioPresignedUploader({
    Dio? dio,
    DateTime Function()? clock,
    this.sendTimeout = const Duration(minutes: 15),
  }) : _dio = dio ?? Dio(),
       _clock = clock ?? DateTime.now;

  final Dio _dio;
  final DateTime Function() _clock;
  final Duration sendTimeout;

  @override
  Future<void> upload({
    required UploadTarget target,
    required File file,
    UploadProgress? onProgress,
    CancelToken? cancelToken,
  }) async {
    if (!_clock().isBefore(target.expiresAt)) {
      throw const AnalysisUploadException(
        AnalysisUploadFailure.urlExpired,
        'The upload link expired before the upload started.',
      );
    }
    final length = await file.length();
    final headers = Map<String, String>.of(target.requiredHeaders);
    // The signature covers Content-Length, so the body must match it exactly.
    final signedLength = int.tryParse(headers['Content-Length'] ?? '');
    if (signedLength != null && signedLength != length) {
      throw const AnalysisUploadException(
        AnalysisUploadFailure.rejected,
        'The audio file changed after it was selected.',
      );
    }
    headers['Content-Length'] = '$length';
    try {
      await _dio.putUri<Object?>(
        target.uploadUrl,
        // The exact bytes, streamed from disk. No form encoding.
        data: file.openRead(),
        options: Options(
          headers: headers,
          sendTimeout: sendTimeout,
          receiveTimeout: const Duration(seconds: 60),
          // Storage answers errors with XML; read it as text, never as JSON.
          responseType: ResponseType.plain,
        ),
        cancelToken: cancelToken,
        onSendProgress: onProgress,
      );
    } on DioException catch (error) {
      throw _translate(error, target);
    }
  }

  Exception _translate(DioException error, UploadTarget target) {
    switch (error.type) {
      case DioExceptionType.cancel:
        return const AnalysisPollingCancelledException();
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const AnalysisUploadException(
          AnalysisUploadFailure.timeout,
          'The upload timed out.',
        );
      case DioExceptionType.connectionError:
      case DioExceptionType.unknown:
      case DioExceptionType.badCertificate:
        if (error.response == null) {
          return const AnalysisUploadException(
            AnalysisUploadFailure.connection,
            'The upload could not reach the storage service.',
          );
        }
      case DioExceptionType.badResponse:
        break;
    }
    final body = error.response?.data;
    final expired =
        !_clock().isBefore(target.expiresAt) ||
        (body is String && body.contains('expired'));
    if (expired) {
      return const AnalysisUploadException(
        AnalysisUploadFailure.urlExpired,
        'The upload link expired.',
      );
    }
    return AnalysisUploadException(
      AnalysisUploadFailure.rejected,
      'The storage service refused the upload '
      '(HTTP ${error.response?.statusCode ?? 0}).',
    );
  }
}
