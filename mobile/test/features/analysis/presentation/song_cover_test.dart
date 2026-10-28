import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/analysis/presentation/song_cover.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
  MaterialApp(
    home: Scaffold(body: Center(child: child)),
  ),
);

void main() {
  testWidgets('a song with no cover shows a made art card', (tester) async {
    await _pump(
      tester,
      const SongCover(seed: 'Sudu Gawuma', genres: ['Sinhala']),
    );

    expect(find.byKey(const ValueKey('artCard')), findsOneWidget);
    expect(find.byKey(const ValueKey('coverImage')), findsNothing);
  });

  testWidgets('a song with a cover shows it over the art card', (tester) async {
    await _pump(
      tester,
      const SongCover(
        seed: 'Duvet',
        genres: ['Rock'],
        coverUrl: 'https://bucket.example/jobs/x/playback/cover.jpg?sig=1',
      ),
    );

    expect(find.byKey(const ValueKey('coverImage')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('artCard')),
      findsOneWidget,
    ); // underneath, in case it fails
    final image = tester.widget<Image>(
      find.byKey(const ValueKey('coverImage')),
    );
    expect(image.image, isA<ResizeImage>());
  });

  testWidgets('a cover that cannot load leaves the art card, not an error', (
    tester,
  ) async {
    await _pump(
      tester,
      const SongCover(
        seed: 'Lemon',
        coverUrl: 'https://bucket.invalid/none.jpg',
      ),
    );
    await tester.pump(const Duration(milliseconds: 300));

    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('artCard')), findsOneWidget);
  });

  testWidgets('a link that is not https is never loaded', (tester) async {
    await _pump(
      tester,
      const SongCover(
        seed: 'Lemon',
        coverUrl: 'http://bucket.example/cover.jpg',
      ),
    );

    expect(find.byKey(const ValueKey('coverImage')), findsNothing);
    expect(find.byKey(const ValueKey('artCard')), findsOneWidget);
  });

  testWidgets('the card has the size asked for, even with an empty name', (
    tester,
  ) async {
    await _pump(tester, const SongCover(seed: '', size: 132));

    final size = tester.getSize(find.byType(SongCover));
    expect(size, const Size(132, 132));
    expect(tester.takeException(), isNull);
  });

  test('the song list reads the cover link, and only keeps an https one', () {
    CloudSong song(Object? url) => CloudSong.fromJson({
      'job_id': 'a',
      'title': 'T',
      'created_at': '2026-10-23T07:45:03+00:00',
      'cover_url': url,
    });

    expect(
      song('https://b.example/c.jpg?sig=1').coverUrl,
      'https://b.example/c.jpg?sig=1',
    );
    expect(song(null).coverUrl, isNull);
    expect(song('http://b.example/c.jpg').coverUrl, isNull);
    expect(song('javascript:alert(1)').coverUrl, isNull);
    expect(song(5).coverUrl, isNull);
    expect(
      CloudSong.fromJson({
        'job_id': 'a',
        'title': 'T',
        'created_at': '2026-10-23T07:45:03+00:00',
      }).coverUrl,
      isNull,
    );
  });
}
