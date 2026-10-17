/// How the app reaches the analysis backend.
enum AnalysisApiMode {
  /// Local development server: one multipart request carries the audio.
  local,

  /// Hosted AWS API: create a job, upload straight to storage, then confirm.
  hosted;

  static AnalysisApiMode parse(String value) => switch (value.trim()) {
    'hosted' => hosted,
    _ => local,
  };
}

class AnalysisApiConfig {
  const AnalysisApiConfig({
    required this.baseUrl,
    this.mode = AnalysisApiMode.local,
    this.authToken = '',
  });

  /// Set at build time, for example:
  /// `--dart-define=CHORDSYNC_API_MODE=hosted
  ///  --dart-define=CHORDSYNC_API_BASE_URL=https://...
  ///  --dart-define=CHORDSYNC_API_TOKEN=...`
  ///
  /// A build-time token is compiled into the app. It is for private demo builds
  /// only; a real release should sign users in instead.
  static final development = AnalysisApiConfig(
    baseUrl: const String.fromEnvironment(
      'CHORDSYNC_API_BASE_URL',
      defaultValue: 'http://127.0.0.1:8000',
    ),
    mode: AnalysisApiMode.parse(
      const String.fromEnvironment('CHORDSYNC_API_MODE'),
    ),
    authToken: const String.fromEnvironment('CHORDSYNC_API_TOKEN'),
  );

  final String baseUrl;
  final AnalysisApiMode mode;
  final String authToken;

  bool get isHosted => mode == AnalysisApiMode.hosted;
}
