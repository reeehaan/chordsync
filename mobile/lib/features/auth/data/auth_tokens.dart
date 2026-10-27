/// A signed-in person's tokens. [accessToken] goes to the ChordSync API and
/// lasts about an hour; [refreshToken] gets a new one and lasts weeks.
class AuthTokens {
  const AuthTokens({
    required this.email,
    required this.accessToken,
    required this.refreshToken,
    required this.accessExpiresAt,
  });

  final String email;
  final String accessToken;
  final String refreshToken;
  final DateTime accessExpiresAt;

  /// True when the access token is gone or about to be, so it should be
  /// renewed before it is used.
  bool needsRefresh(
    DateTime now, {
    Duration margin = const Duration(minutes: 2),
  }) => !now.isBefore(accessExpiresAt.subtract(margin));

  AuthTokens withAccess(String accessToken, DateTime expiresAt) => AuthTokens(
    email: email,
    accessToken: accessToken,
    refreshToken: refreshToken,
    accessExpiresAt: expiresAt,
  );

  Map<String, Object?> toJson() => {
    'email': email,
    'accessToken': accessToken,
    'refreshToken': refreshToken,
    'accessExpiresAt': accessExpiresAt.toUtc().toIso8601String(),
  };

  static AuthTokens? tryFromJson(Object? value) {
    if (value is! Map) return null;
    final email = value['email'];
    final access = value['accessToken'];
    final refresh = value['refreshToken'];
    final expires = DateTime.tryParse('${value['accessExpiresAt']}');
    if (email is! String ||
        access is! String ||
        refresh is! String ||
        expires == null ||
        email.isEmpty ||
        access.isEmpty ||
        refresh.isEmpty) {
      return null;
    }
    return AuthTokens(
      email: email,
      accessToken: access,
      refreshToken: refresh,
      accessExpiresAt: expires,
    );
  }
}
