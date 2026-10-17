import 'package:dio/dio.dart';

import 'analysis_client_errors.dart';

/// Turns a failed analysis-server request into a domain exception.
Exception translateAnalysisDioException(DioException error) {
  final response = error.response;
  if (response != null) {
    return analysisApiException(response.statusCode ?? 0, response.data);
  }
  if (error.error is FormatException) {
    return const AnalysisDataException('Malformed JSON response.');
  }
  return const AnalysisTransportException(
    'Could not communicate with the analysis server.',
  );
}

/// Builds an [AnalysisApiException] from a status code and an error body.
AnalysisApiException analysisApiException(int statusCode, Object? data) {
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

Map<String, dynamic> analysisJsonMap(Object? data) {
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  throw const AnalysisDataException('Expected a JSON object response.');
}
