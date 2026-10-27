import '../../practice_timeline/data/shared_timeline.dart';

/// One finished song in the shared library, as the API lists it.
class CloudSong {
  const CloudSong({
    required this.jobId,
    required this.title,
    required this.createdAt,
    this.durationSeconds,
    this.artist,
    this.genres = const [],
  });

  factory CloudSong.fromJson(Map<String, dynamic> json) => CloudSong(
    jobId: json['job_id'] as String,
    title: json['title'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
    artist: json['artist'] as String?,
    genres: _genres(json['genres']),
  );

  final String jobId;
  final String title;
  final DateTime createdAt;
  final double? durationSeconds;

  /// Who made the song, once the song has been tagged. Null before that.
  final String? artist;

  /// What kind of music it is (up to three), once the song has been tagged.
  final List<String> genres;

  static List<String> _genres(Object? value) => [
    if (value is List)
      for (final genre in value)
        if (genre is String && genre.isNotEmpty) genre,
  ];
}

/// A short-lived link to a song's audio. It carries its own permission, so it
/// is fetched with a plain client and never with the app's bearer token.
class CloudAudioLink {
  const CloudAudioLink({
    required this.url,
    required this.expiresInSeconds,
    this.fileType,
  });

  factory CloudAudioLink.fromJson(Map<String, dynamic> json) {
    final url = json['url'] as String;
    // A song's audio must travel encrypted, like an upload does.
    if (Uri.tryParse(url)?.scheme != 'https') {
      throw const FormatException('The audio link is not an https link.');
    }
    return CloudAudioLink(
      url: url,
      expiresInSeconds: (json['expires_in_seconds'] as num).toInt(),
      fileType: json['file_type'] as String?,
    );
  }

  final String url;
  final int expiresInSeconds;
  final String? fileType;
}

/// The shared library routes: songs analysed by any token holder.
abstract interface class CloudLibraryApi {
  /// Every finished song, newest first.
  Future<List<CloudSong>> listSongs();

  Future<SharedTimeline> getSongTimeline(String jobId);

  Future<CloudAudioLink> getSongAudioLink(String jobId);
}
