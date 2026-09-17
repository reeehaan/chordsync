class AnalysisApiConfig {
  const AnalysisApiConfig({required this.baseUrl});

  static const development = AnalysisApiConfig(
    baseUrl: String.fromEnvironment(
      'CHORDSYNC_API_BASE_URL',
      defaultValue: 'http://127.0.0.1:8000',
    ),
  );

  final String baseUrl;
}
