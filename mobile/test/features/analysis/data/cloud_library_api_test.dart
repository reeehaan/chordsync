import 'package:chordsync/features/analysis/data/analysis_client_errors.dart';
import 'package:chordsync/features/analysis/data/hosted_analysis_api.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/recording_http_adapter.dart';

const _token = 'test-token-0123456789abcdefghijklmnop';

DioHostedAnalysisApi _api(
  RecordingHttpAdapter adapter, {
  String? token = _token,
}) => DioHostedAnalysisApi(
  baseUrl: 'https://api.test.invalid',
  tokenProvider: () => token,
  dio: dioWith(adapter),
);

void main() {
  test(
    'lists the songs, with the bearer token, newest first as sent',
    () async {
      final adapter = RecordingHttpAdapter(
        (_) => jsonBody({
          'songs': [
            {
              'job_id': 'job-b',
              'title': 'Sudu Gawuma - La Signore',
              'created_at': '2026-10-23T07:45:03.939028+00:00',
              'duration_seconds': 215.5,
            },
            {
              'job_id': 'job-a',
              'title': 'Older',
              'created_at': '2026-10-17T17:14:37+00:00',
              'duration_seconds': null,
            },
          ],
        }, 200),
      );

      final songs = await _api(adapter).listSongs();

      final sent = adapter.requests.single;
      expect(sent.method, 'GET');
      expect(sent.uri.toString(), 'https://api.test.invalid/analysis/library');
      expect(sent.headers['Authorization'], 'Bearer $_token');
      expect(songs.map((song) => song.jobId), ['job-b', 'job-a']);
      expect(songs.first.title, 'Sudu Gawuma - La Signore');
      expect(songs.first.durationSeconds, 215.5);
      expect(songs.last.durationSeconds, isNull);
    },
  );

  test('reads each song\'s artist and genres when it has them', () async {
    final adapter = RecordingHttpAdapter(
      (_) => jsonBody({
        'songs': [
          {
            'job_id': 'tagged',
            'title': 'Wonderwall - Oasis',
            'created_at': '2026-10-23T07:45:03+00:00',
            'artist': 'Oasis',
            'genres': ['Rock', 'Indie'],
          },
          {
            'job_id': 'old',
            'title': 'Duvet',
            'created_at': '2026-10-17T17:14:37+00:00',
          },
          {
            'job_id': 'odd',
            'title': 'Odd',
            'created_at': '2026-10-17T17:14:37+00:00',
            'artist': null,
            'genres': ['Pop', 5, '', null],
          },
        ],
      }, 200),
    );

    final songs = await _api(adapter).listSongs();

    expect(songs[0].artist, 'Oasis');
    expect(songs[0].genres, ['Rock', 'Indie']);
    expect(songs[1].artist, isNull);
    expect(songs[1].genres, isEmpty); // not tagged yet
    expect(songs[2].genres, ['Pop']); // anything that is not a name is dropped
  });

  test('reads a song timeline and its audio link', () async {
    final adapter = RecordingHttpAdapter((request) {
      if (request.uri.path.endsWith('/result')) {
        return jsonBody(hostedTimelineJson, 200);
      }
      return jsonBody({
        'url': 'https://bucket.invalid/jobs/job-b/playback/audio.mp3?sig=1',
        'expires_in_seconds': 600,
        'file_type': 'mp3',
      }, 200);
    });
    final api = _api(adapter);

    final timeline = await api.getSongTimeline('job-b');
    final link = await api.getSongAudioLink('job-b');

    expect(adapter.requests.map((r) => r.uri.path), [
      '/analysis/library/job-b/result',
      '/analysis/library/job-b/audio',
    ]);
    expect(timeline.bpm, isPositive);
    expect(link.url, startsWith('https://bucket.invalid/'));
    expect(link.expiresInSeconds, 600);
    expect(link.fileType, 'mp3');
  });

  test('a missing song is an API error, not a crash', () async {
    final adapter = RecordingHttpAdapter(
      (_) => jsonBody({
        'error': {'code': 'song_not_found', 'message': 'Song was not found.'},
      }, 404),
    );

    await expectLater(
      _api(adapter).getSongAudioLink('nope'),
      throwsA(
        isA<AnalysisApiException>().having(
          (error) => error.statusCode,
          'statusCode',
          404,
        ),
      ),
    );
  });

  test('does not call the API without a token', () async {
    final adapter = RecordingHttpAdapter((_) => jsonBody({'songs': []}, 200));

    await expectLater(
      _api(adapter, token: null).listSongs(),
      throwsA(isA<AnalysisApiException>()),
    );
    expect(adapter.requests, isEmpty);
  });

  test('a malformed list is reported as bad data', () async {
    final adapter = RecordingHttpAdapter(
      (_) => jsonBody({'songs': 'not a list'}, 200),
    );

    await expectLater(
      _api(adapter).listSongs(),
      throwsA(isA<AnalysisDataException>()),
    );
  });

  test('an audio link that is not https is refused', () async {
    final adapter = RecordingHttpAdapter(
      (_) => jsonBody({
        'url': 'http://bucket.invalid/jobs/job-b/playback/audio.mp3',
        'expires_in_seconds': 600,
        'file_type': 'mp3',
      }, 200),
    );

    await expectLater(
      _api(adapter).getSongAudioLink('job-b'),
      throwsA(isA<AnalysisDataException>()),
    );
  });
}
