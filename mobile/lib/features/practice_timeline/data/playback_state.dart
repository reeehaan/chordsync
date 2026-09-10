class PlaybackState {
  const PlaybackState({
    required this.playbackTime,
    required this.chord,
    required this.beatNumber,
    required this.isDownbeat,
    required this.lyricWord,
  });

  final double playbackTime;
  final String chord;
  final int? beatNumber;
  final bool isDownbeat;
  final String? lyricWord;
}
