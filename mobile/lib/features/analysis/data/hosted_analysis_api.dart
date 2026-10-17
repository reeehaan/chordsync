import 'dart:async';

import 'package:dio/dio.dart';

import '../../practice_timeline/data/shared_timeline.dart';
import 'analysis_client_errors.dart';
import 'analysis_http_mapping.dart';
import 'analysis_job.dart';
import 'hosted_upload_models.dart';

/// Returns the current bearer token, or null/empty if there is none.
typedef AnalysisAuthTokenProvider = FutureOr<String?> Function();

/// The hosted analysis API, one method per route. No audio passes through it.
abstract interface class HostedAnalysisApi {
  Future<UploadTarget> createUpload(CreateUploadRequest request);

  Future<ConfirmOutcome> confirmUpload(String jobId);

  Future<AnalysisJob> getJob(String jobId);

  Future<SharedTimeline> getResult(String jobId);

  /// Stops the job on the server; repeating the call returns the same state.
  Future<AnalysisJob> cancelJob(String jobId);
}

class DioHostedAnalysisApi implements HostedAnalysisApi {
  /// [tokenProvider] is called for every request, so a refreshed token is
  /// picked up without rebuilding the client.
  DioHostedAnalysisApi({
    required String baseUrl,
    required this._tokenProvider,
    Dio? dio,
  }) : _dio = dio ?? Dio() {
    _dio.options.baseUrl = baseUrl;
  }

  final Dio _dio;
  final AnalysisAuthTokenProvider _tokenProvider;

  @override
  Future<UploadTarget> createUpload(CreateUploadRequest request) async {
    final response = await _send(
      () async => _dio.post<Object?>(
        '/analysis/jobs',
        data: request.toJson(),
        options: await _authorized(),
      ),
      malformed: 'Malformed upload target response.',
    );
    if (response.statusCode != 201) {
      throw const AnalysisDataException('Unexpected create-job response.');
    }
    return _parse(
      () => UploadTarget.fromJson(analysisJsonMap(response.data)),
      'Malformed upload target response.',
    );
  }

  @override
  Future<ConfirmOutcome> confirmUpload(String jobId) async {
    final response = await _send(
      () async => _dio.post<Object?>(
        '/analysis/jobs/${Uri.encodeComponent(jobId)}/confirm-upload',
        options: await _authorized(),
      ),
      malformed: 'Malformed confirm response.',
    );
    final status = response.statusCode;
    if (status != 202 && status != 200) {
      throw const AnalysisDataException('Unexpected confirm response.');
    }
    return _parse(
      () => ConfirmOutcome(
        job: AnalysisJob.fromJson(analysisJsonMap(response.data)),
        newlyQueued: status == 202,
      ),
      'Malformed confirm response.',
    );
  }

  @override
  Future<AnalysisJob> getJob(String jobId) async {
    final response = await _send(
      () async => _dio.get<Object?>(
        '/analysis/jobs/${Uri.encodeComponent(jobId)}',
        options: await _authorized(),
      ),
      malformed: 'Malformed analysis job response.',
    );
    return _parse(
      () => AnalysisJob.fromJson(analysisJsonMap(response.data)),
      'Malformed analysis job response.',
    );
  }

  @override
  Future<SharedTimeline> getResult(String jobId) async {
    final response = await _send(
      () async => _dio.get<Object?>(
        '/analysis/jobs/${Uri.encodeComponent(jobId)}/result',
        options: await _authorized(),
      ),
      malformed: 'Malformed SharedTimeline response.',
    );
    return _parse(
      () => SharedTimeline.fromJson(analysisJsonMap(response.data)),
      'Malformed SharedTimeline response.',
    );
  }

  @override
  Future<AnalysisJob> cancelJob(String jobId) async {
    final response = await _send(
      () async => _dio.post<Object?>(
        '/analysis/jobs/${Uri.encodeComponent(jobId)}/cancel',
        options: await _authorized(),
      ),
      malformed: 'Malformed cancel response.',
    );
    return _parse(
      () => AnalysisJob.fromJson(analysisJsonMap(response.data)),
      'Malformed cancel response.',
    );
  }

  /// The bearer header is added here, only for requests to the ChordSync API.
  /// The S3 upload uses a different client and never sees it.
  Future<Options> _authorized() async {
    final token = (await _tokenProvider())?.trim();
    if (token == null || token.isEmpty) {
      throw const AnalysisApiException(
        statusCode: 401,
        code: 'authentication_required',
        message: 'No access token is configured.',
      );
    }
    return Options(headers: {'Authorization': 'Bearer $token'});
  }

  Future<Response<Object?>> _send(
    Future<Response<Object?>> Function() request, {
    required String malformed,
  }) async {
    try {
      return await request();
    } on AnalysisApiException {
      rethrow;
    } on DioException catch (error) {
      throw translateAnalysisDioException(error);
    } on Object {
      throw AnalysisDataException(malformed);
    }
  }

  T _parse<T>(T Function() parse, String malformed) {
    try {
      return parse();
    } on AnalysisDataException {
      rethrow;
    } on Object {
      throw AnalysisDataException(malformed);
    }
  }
}
