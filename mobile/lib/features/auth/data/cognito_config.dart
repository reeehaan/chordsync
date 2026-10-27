/// Where the app signs people in. Public values only: the app client has no
/// secret, so nothing here needs protecting.
///
/// Set at build time:
/// `--dart-define=CHORDSYNC_COGNITO_CLIENT_ID=...`
/// `--dart-define=CHORDSYNC_COGNITO_REGION=ap-southeast-1` (the default)
///
/// Without a client id the app does not ask anyone to sign in, which keeps the
/// private demo builds and local development working as before.
class CognitoConfig {
  const CognitoConfig({required this.clientId, this.region = 'ap-southeast-1'});

  static const fromEnvironment = CognitoConfig(
    clientId: String.fromEnvironment('CHORDSYNC_COGNITO_CLIENT_ID'),
    region: String.fromEnvironment(
      'CHORDSYNC_COGNITO_REGION',
      defaultValue: 'ap-southeast-1',
    ),
  );

  final String clientId;
  final String region;

  bool get isConfigured => clientId.isNotEmpty;

  /// Cognito's own address for this region. Always https.
  String get endpoint => 'https://cognito-idp.$region.amazonaws.com/';
}
