/// A song's title and artist, read from a downloaded file name such as
/// "Lemon - Kenshi Yonezu - Spotimate.app".
class SongIdentity {
  const SongIdentity({required this.title, this.artist});

  final String title;
  final String? artist;

  static final _extension = RegExp(
    r'\.(mp3|m4a|wav|flac|aac|ogg|opus|mp4)$',
    caseSensitive: false,
  );
  // A whole part of the name that is only a download site, e.g.
  // "Spotimate.app". A real title such as "Youtube" is left alone.
  static final _siteName = RegExp(
    r'^(spotimate|spotifydown|spotdl|y2mate|ytmp3|mp3juices|savefrom)'
    r'(\.\w+)?$',
    caseSensitive: false,
  );
  static final _separator = RegExp(r'\s+[-–—]\s+');

  /// "Title - Artist - site" gives a title and an artist. A name that does not
  /// split that way is the title on its own, unchanged.
  factory SongIdentity.fromFileName(String name) {
    final bare = name.replaceFirst(_extension, '').trim();
    final parts = bare
        .split(_separator)
        .map((part) => part.trim())
        .where((part) => part.isNotEmpty && !_siteName.hasMatch(part))
        .toList();
    if (parts.length < 2) return SongIdentity(title: name);
    return SongIdentity(title: parts[0], artist: parts[1]);
  }
}
