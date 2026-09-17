import 'dart:io';

import 'package:dio/dio.dart';

import '../../practice_timeline/data/shared_timeline.dart';
import 'analysis_client_errors.dart';
import 'analysis_job.dart';

typedef AnalysisUploadProgress = void Function(int sent, int total);

abstract interface class AnalysisApiClient {
  Future<AnalysisJob> createJob({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onSendProgress,
  });

  Future<AnalysisJob> getJob(String jobId);

  Future<SharedTimeline> getResult(String jobId);
}

class DioAnalysisApiClient implements AnalysisApiClient {
  DioAnalysisApiClient({required String baseUrl, Dio? dio})
    : _dio = dio ?? Dio() {
    _dio.options.baseUrl = baseUrl;
  }

  final Dio _dio;

  @override
  Future<AnalysisJob> createJob({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onSendProgress,
  }) async {
    try {
      final filename = audioFile.uri.pathSegments.last;
      final form = FormData.fromMap({
        'title': title,
        'audio': await MultipartFile.fromFile(
          audioFile.path,
          filename: filename,
        ),
      });
      final response = await _dio.post<Object?>(
        '/analysis/jobs',
        data: form,
        onSendProgress: onSendProgress,
      );
      if (response.statusCode != 202) {
        throw _apiException(response.statusCode ?? 0, response.data);
      }
      return AnalysisJob.fromJson(_jsonMap(response.data));
    } on AnalysisApiException {
      rethrow;
    } on AnalysisDataException {
      rethrow;
    } on DioException catch (error) {
      throw _translateDioException(error);
    } on Object {
      throw const AnalysisDataException('Could not prepare the audio upload.');
    }
  }

  @override
  Future<AnalysisJob> getJob(String jobId) async {
    try {
      final response = await _dio.get<Object?>(
        '/analysis/jobs/${Uri.encodeComponent(jobId)}',
      );
      return AnalysisJob.fromJson(_jsonMap(response.data));
    } on AnalysisApiException {
      rethrow;
    } on AnalysisDataException {
      rethrow;
    } on DioException catch (error) {
      throw _translateDioException(error);
    } on Object {
      throw const AnalysisDataException('Malformed analysis job response.');
    }
  }

  @override
  Future<SharedTimeline> getResult(String jobId) async {
    try {
      final response = await _dio.get<Object?>(
        '/analysis/jobs/${Uri.encodeComponent(jobId)}/result',
      );
      return SharedTimeline.fromJson(_jsonMap(response.data));
    } on AnalysisApiException {
      rethrow;
    } on AnalysisDataException {
      rethrow;
    } on DioException catch (error) {
      throw _translateDioException(error);
    } on Object {
      throw const AnalysisDataException('Malformed SharedTimeline response.');
    }
  }

  Exception _translateDioException(DioException error) {
    final response = error.response;
    if (response != null) {
      return _apiException(response.statusCode ?? 0, response.data);
    }
    if (error.error is FormatException) {
      return const AnalysisDataException('Malformed JSON response.');
    }
    return const AnalysisTransportException(
      'Could not communicate with the analysis server.',
    );
  }

  AnalysisApiException _apiException(int statusCode, Object? data) {
    if (data case {'error': final Map error}) {
      final code = error['code'];
      final message = error['message'];
      if (code is String && message is String) {
        return AnalysisApiException(
          statusCode: statusCode,
          code: code,
          message: message,
        );
      }
    }
    if (statusCode == 422) {
      return const AnalysisApiException(
        statusCode: 422,
        code: 'request_validation_failed',
        message: 'The analysis request was invalid.',
      );
    }
    return AnalysisApiException(
      statusCode: statusCode,
      code: 'unexpected_api_error',
      message: 'The analysis server returned an unexpected error.',
    );
  }

  Map<String, dynamic> _jsonMap(Object? data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    throw const AnalysisDataException('Expected a JSON object response.');
  }
}
