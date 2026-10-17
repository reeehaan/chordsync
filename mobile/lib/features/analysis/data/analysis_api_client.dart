import 'dart:io';

import 'package:dio/dio.dart';

import '../../practice_timeline/data/shared_timeline.dart';
import 'analysis_cancellation.dart';
import 'analysis_client_errors.dart';
import 'analysis_http_mapping.dart';
import 'analysis_job.dart';

typedef AnalysisUploadProgress = void Function(int sent, int total);

abstract interface class AnalysisApiClient {
  Future<AnalysisJob> createJob({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onSendProgress,
    AnalysisPollingCancellationToken? cancellation,
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
    AnalysisPollingCancellationToken? cancellation,
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
        throw analysisApiException(response.statusCode ?? 0, response.data);
      }
      return AnalysisJob.fromJson(analysisJsonMap(response.data));
    } on AnalysisApiException {
      rethrow;
    } on AnalysisDataException {
      rethrow;
    } on DioException catch (error) {
      throw translateAnalysisDioException(error);
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
      return AnalysisJob.fromJson(analysisJsonMap(response.data));
    } on AnalysisApiException {
      rethrow;
    } on AnalysisDataException {
      rethrow;
    } on DioException catch (error) {
      throw translateAnalysisDioException(error);
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
      return SharedTimeline.fromJson(analysisJsonMap(response.data));
    } on AnalysisApiException {
      rethrow;
    } on AnalysisDataException {
      rethrow;
    } on DioException catch (error) {
      throw translateAnalysisDioException(error);
    } on Object {
      throw const AnalysisDataException('Malformed SharedTimeline response.');
    }
  }
}
