import 'package:chordsync/features/analysis/application/genre_shelves.dart';
import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/analysis/presentation/genre_style.dart';
import 'package:chordsync/features/auth/data/user_profile.dart';
import 'package:flutter_test/flutter_test.dart';

CloudSong _song(String id, List<String> genres, {int day = 1}) => CloudSong(
  jobId: id,
  title: id,
  createdAt: DateTime.utc(2026, 10, day),
  genres: genres,
);

void main() {
  final songs = [
    _song('a', ['Sinhala', 'Pop'], day: 1),
    _song('b', ['Sinhala'], day: 3),
    _song('c', ['Sinhala'], day: 2),
    _song('d', ['Rock', 'Indie'], day: 4),
    _song('e', ['Pop'], day: 5),
    _song('f', ['Other'], day: 6),
    _song('g', <String>[], day: 7),
  ];

  test('a song with two genres is on both shelves', () {
    final layout = buildDiscoverLayout(songs);

    List<String> ids(String genre) => [
      for (final song
          in layout.shelves.firstWhere((s) => s.genre == genre).songs)
        song.jobId,
    ];
    expect(ids('Sinhala'), containsAll(['a', 'b', 'c']));
    expect(ids('Pop'), containsAll(['a', 'e']));
    expect(ids('Rock'), ['d']);
    expect(ids('Indie'), ['d']);
  });

  test('inside a shelf the newest song comes first', () {
    final layout = buildDiscoverLayout(songs);

    expect(
      [for (final s in layout.shelves.first.songs) s.jobId],
      ['b', 'c', 'a'],
    );
  });

  test(
    'without favourites the biggest shelves come first and Other is last',
    () {
      final layout = buildDiscoverLayout(songs);

      expect(
        [for (final s in layout.shelves) s.genre],
        ['Sinhala', 'Pop', 'Indie', 'Rock', 'Other'],
      );
      expect(layout.favourites, isEmpty);
      expect(layout.heroLine, isNull);
    },
  );

  test('the favourite genres come first, in the order the person chose', () {
    final layout = buildDiscoverLayout(songs, favourites: ['Rock', 'Pop']);

    expect(
      [for (final s in layout.shelves) s.genre],
      ['Rock', 'Pop', 'Sinhala', 'Indie', 'Other'],
    );
    expect([for (final s in layout.favourites) s.genre], ['Rock', 'Pop']);
  });

  test('a favourite with no songs is skipped, and repeats are ignored', () {
    final layout = buildDiscoverLayout(
      songs,
      favourites: ['Jazz', 'Pop', 'Pop'],
    );

    expect([for (final s in layout.favourites) s.genre], ['Pop']);
    expect(layout.shelves.where((s) => s.genre == 'Pop'), hasLength(1));
  });

  test('songs without a genre are kept apart, newest first', () {
    final layout = buildDiscoverLayout([
      ...songs,
      _song('h', <String>[], day: 9),
    ]);

    expect([for (final s in layout.untagged) s.jobId], ['h', 'g']);
    expect(
      layout.shelves.expand((s) => s.songs).any((s) => s.genres.isEmpty),
      isFalse,
    );
  });

  test('the banner line names up to three favourites', () {
    String? line(List<String> favourites) => buildDiscoverLayout([
      _song('1', ['Pop']),
      _song('2', ['Rock']),
      _song('3', ['Indie']),
      _song('4', ['Folk']),
    ], favourites: favourites).heroLine;

    expect(line(['Pop']), 'Because you like Pop');
    expect(line(['Pop', 'Rock']), 'Because you like Pop and Rock');
    expect(
      line(['Pop', 'Rock', 'Indie']),
      'Because you like Pop, Rock and Indie',
    );
    expect(
      line(['Pop', 'Rock', 'Indie', 'Folk']),
      'Because you like Pop, Rock and Indie',
    );
    expect(line(['Jazz']), isNull);
  });

  test('nothing to show is reported as empty', () {
    expect(buildDiscoverLayout(const []).isEmpty, isTrue);
    expect(buildDiscoverLayout(songs).isEmpty, isFalse);
  });

  test(
    'every genre people can pick has a banner colour, and unknown names a neutral one',
    () {
      for (final genre in musicGenres) {
        expect(GenreStyle.names, contains(genre));
      }
      expect(GenreStyle.of('Polka').light, GenreStyle.of('Other').light);
    },
  );
}
