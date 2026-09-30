class PlaybackState {
  const PlaybackState({
    required this.playbackTime,
    required this.chord,
    required this.currentBarNumber,
    required this.beatNumber,
    required this.beatsPerBar,
    required this.isDownbeat,
    required this.chordProgression,
    required this.previousChord,
    required this.nextChord,
    this.currentChordStart,
    this.currentChordEnd,
    required this.previousLyricWord,
    required this.lyricWord,
    required this.nextLyricWord,
    required this.isMusicOnly,
    this.musicOnlyStart,
    this.musicOnlyEnd,
    this.currentBeatStart,
    this.nextBeatStart,
  });

  final double playbackTime;
  final String chord;
  final int? currentBarNumber;
  final int? beatNumber;
  final int beatsPerBar;
  final bool isDownbeat;
  final List<String> chordProgression;
  final String? previousChord;
  final String? nextChord;
  final double? currentChordStart;
  final double? currentChordEnd;
  final String? previousLyricWord;
  final String? lyricWord;
  final String? nextLyricWord;
  final bool isMusicOnly;
  final double? musicOnlyStart;
  final double? musicOnlyEnd;
  final double? currentBeatStart;
  final double? nextBeatStart;

  String get currentChord => chord;
  String? get activeLyricWord => lyricWord;

  /// Fraction of the current chord's span already played, or null when
  /// there is no active chord (before the first beat, or past the end).
  double? get chordProgress {
    final start = currentChordStart;
    final end = currentChordEnd;
    if (start == null || end == null || end <= start) return null;
    return ((playbackTime - start) / (end - start)).clamp(0.0, 1.0);
  }

  double? get musicOnlyProgress {
    final start = musicOnlyStart;
    final end = musicOnlyEnd;
    if (!isMusicOnly || start == null || end == null || end <= start) {
      return null;
    }
    return ((playbackTime - start) / (end - start)).clamp(0.0, 1.0);
  }

  double? get beatProgress {
    final start = currentBeatStart;
    final end = nextBeatStart;
    if (start == null || end == null || end <= start) return null;
    return ((playbackTime - start) / (end - start)).clamp(0.0, 1.0);
  }
}
