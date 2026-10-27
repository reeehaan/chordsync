import '../data/cloud_library_api.dart';

/// The songs of one genre, as a row on the home screen.
class GenreShelf {
  const GenreShelf(this.genre, this.songs);

  final String genre;
  final List<CloudSong> songs;
}

/// What the discover area shows: one shelf per genre, and the songs that have
/// not been given a genre yet.
class DiscoverLayout {
  const DiscoverLayout({
    required this.shelves,
    required this.untagged,
    required this.favourites,
  });

  /// The genres the person picked that have songs, in the order they chose.
  final List<GenreShelf> favourites;

  /// Every genre with songs: the person's favourites first, then the rest.
  final List<GenreShelf> shelves;

  final List<CloudSong> untagged;

  bool get isEmpty => shelves.isEmpty && untagged.isEmpty;

  /// "Because you like Pop and Indie", or null when none of their favourite
  /// genres has a song.
  String? get heroLine {
    final names = [for (final shelf in favourites.take(3)) shelf.genre];
    if (names.isEmpty) return null;
    if (names.length == 1) return 'Because you like ${names.single}';
    final head = names.sublist(0, names.length - 1).join(', ');
    return 'Because you like $head and ${names.last}';
  }
}

/// Groups songs by genre. A song with two genres is on both shelves. Within a
/// shelf the newest song comes first. Shelves for the person's favourites come
/// first, then the others from the biggest to the smallest ("Other" last).
DiscoverLayout buildDiscoverLayout(
  List<CloudSong> songs, {
  List<String> favourites = const [],
}) {
  final byGenre = <String, List<CloudSong>>{};
  final untagged = <CloudSong>[];
  for (final song in songs) {
    if (song.genres.isEmpty) {
      untagged.add(song);
      continue;
    }
    for (final genre in song.genres.toSet()) {
      byGenre.putIfAbsent(genre, () => []).add(song);
    }
  }
  int newestFirst(CloudSong a, CloudSong b) =>
      b.createdAt.compareTo(a.createdAt);
  for (final list in byGenre.values) {
    list.sort(newestFirst);
  }
  untagged.sort(newestFirst);

  final liked = <GenreShelf>[
    for (final genre in favourites.toSet())
      if (byGenre.containsKey(genre)) GenreShelf(genre, byGenre[genre]!),
  ];
  final likedNames = {for (final shelf in liked) shelf.genre};
  final others =
      [
        for (final entry in byGenre.entries)
          if (!likedNames.contains(entry.key))
            GenreShelf(entry.key, entry.value),
      ]..sort((a, b) {
        if (a.genre == 'Other') return 1;
        if (b.genre == 'Other') return -1;
        final bySize = b.songs.length.compareTo(a.songs.length);
        return bySize != 0 ? bySize : a.genre.compareTo(b.genre);
      });
  return DiscoverLayout(
    shelves: [...liked, ...others],
    untagged: untagged,
    favourites: liked,
  );
}
