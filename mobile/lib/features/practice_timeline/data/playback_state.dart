class PlaybackState {
  const PlaybackState({
    required this.playbackTime,
    required this.chord,
    required this.currentBarNumber,
    required this.beatNumber,
    required this.beatsPerBar,
    required this.isDownbeat,
    required this.chordProgression,
    required this.nextChord,
    required this.previousLyricWord,
    required this.lyricWord,
    required this.nextLyricWord,
  });

  final double playbackTime;
  final String chord;
  final int? currentBarNumber;
  final int? beatNumber;
  final int beatsPerBar;
  final bool isDownbeat;
  final List<String> chordProgression;
  final String? nextChord;
  final String? previousLyricWord;
  final String? lyricWord;
  final String? nextLyricWord;

  String get currentChord => chord;
  String? get activeLyricWord => lyricWord;
}
