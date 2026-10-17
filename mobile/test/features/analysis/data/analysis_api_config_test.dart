import 'package:chordsync/features/analysis/data/analysis_api_config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('only the exact word "hosted" selects the hosted flow', () {
    expect(AnalysisApiMode.parse('hosted'), AnalysisApiMode.hosted);
    expect(AnalysisApiMode.parse(' hosted '), AnalysisApiMode.hosted);
    for (final other in ['', 'local', 'HOSTED', 'aws', 'true']) {
      expect(
        AnalysisApiMode.parse(other),
        AnalysisApiMode.local,
        reason: other,
      );
    }
  });

  test('default build settings keep the local multipart flow', () {
    final config = AnalysisApiConfig.development;
    expect(config.isHosted, isFalse);
    expect(config.authToken, isEmpty);
    expect(config.baseUrl, 'http://127.0.0.1:8000');
  });

  test('a hosted config reports itself as hosted', () {
    const config = AnalysisApiConfig(
      baseUrl: 'https://api.example',
      mode: AnalysisApiMode.hosted,
      authToken: 't',
    );
    expect(config.isHosted, isTrue);
  });
}
