import 'playback_state.dart';
import 'shared_timeline.dart';

class PlaybackLookup {
  const PlaybackLookup._();

  static const int chordProgressionLimit = 4;
  static const double barBoundaryToleranceSeconds = 0.001;

  /// Returns the bar containing [playbackTime].
  ///
  /// Bar ranges are start-inclusive and end-exclusive. The final bar alone is
  /// end-inclusive so playback completion retains its musical position.
  static TimelineBar? currentBar(SharedTimeline timeline, double playbackTime) {
    for (var index = 0; index < timeline.bars.length; index++) {
      final bar = timeline.bars[index];
      final isFinalBar = index == timeline.bars.length - 1;
      final isWithinBar =
          bar.startTime <= playbackTime &&
          (playbackTime < bar.endTime ||
              (isFinalBar && playbackTime == bar.endTime));

      if (isWithinBar) return bar;
    }

    return null;
  }

  static double? previousBarStart(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    final activeBar = currentBar(timeline, playbackTime);
    if (activeBar != null) {
      final activeIndex = timeline.bars.indexOf(activeBar);
      if (playbackTime > activeBar.startTime + barBoundaryToleranceSeconds) {
        return activeBar.startTime;
      }
      return activeIndex > 0 ? timeline.bars[activeIndex - 1].startTime : null;
    }

    for (final bar in timeline.bars.reversed) {
      if (bar.startTime < playbackTime - barBoundaryToleranceSeconds) {
        return bar.startTime;
      }
    }
    return null;
  }

  static double? nextBarStart(SharedTimeline timeline, double playbackTime) {
    for (final bar in timeline.bars) {
      if (bar.startTime > playbackTime + barBoundaryToleranceSeconds) {
        return bar.startTime;
      }
    }
    return null;
  }

  static TimelineEvent? currentBeat(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    TimelineEvent? currentBeat;

    for (final bar in timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.time <= playbackTime) {
          currentBeat = beat;
        } else {
          return currentBeat;
        }
      }
    }

    return currentBeat;
  }

  static LyricWord? activeLyricWord(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    for (final segment in timeline.lyrics) {
      for (final word in segment.words) {
        if (word.start <= playbackTime && playbackTime < word.end) {
          return word;
        }
      }
    }

    return null;
  }

  static TimelineEvent? nextChord(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    final currentChord = currentBeat(timeline, playbackTime)?.chord ?? 'N';

    for (final bar in timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.time > playbackTime && beat.chord != currentChord) {
          return beat;
        }
      }
    }

    return null;
  }

  static List<String> chordProgression(
    SharedTimeline timeline,
    double playbackTime, {
    int limit = chordProgressionLimit,
  }) {
    if (limit <= 0) return const [];

    final progression = <String>[];
    final activeBeat = currentBeat(timeline, playbackTime);
    if (activeBeat != null) progression.add(activeBeat.chord);

    for (final bar in timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.time <= playbackTime) continue;
        if (progression.isEmpty || progression.last != beat.chord) {
          progression.add(beat.chord);
          if (progression.length == limit) {
            return List.unmodifiable(progression);
          }
        }
      }
    }

    return List.unmodifiable(progression);
  }

  static LyricWord? previousLyricWord(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    LyricWord? previousWord;

    for (final segment in timeline.lyrics) {
      for (final word in segment.words) {
        if (word.end <= playbackTime &&
            (previousWord == null || word.end > previousWord.end)) {
          previousWord = word;
        }
      }
    }

    return previousWord;
  }

  static LyricWord? nextLyricWord(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    LyricWord? nextWord;

    for (final segment in timeline.lyrics) {
      for (final word in segment.words) {
        if (word.start > playbackTime &&
            (nextWord == null || word.start < nextWord.start)) {
          nextWord = word;
        }
      }
    }

    return nextWord;
  }

  static PlaybackState playbackState(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    final bar = currentBar(timeline, playbackTime);
    final beat = currentBeat(timeline, playbackTime);
    final activeWord = activeLyricWord(timeline, playbackTime);
    final upcomingChord = nextChord(timeline, playbackTime);
    final previousWord = previousLyricWord(timeline, playbackTime);
    final upcomingWord = nextLyricWord(timeline, playbackTime);

    return PlaybackState(
      playbackTime: playbackTime,
      chord: beat?.chord ?? 'N',
      currentBarNumber: bar?.barNumber,
      beatNumber: beat?.beatNumber,
      beatsPerBar: timeline.beatsPerBar,
      isDownbeat: beat?.isDownbeat ?? false,
      chordProgression: chordProgression(timeline, playbackTime),
      nextChord: upcomingChord?.chord,
      previousLyricWord: previousWord?.text,
      lyricWord: activeWord?.text,
      nextLyricWord: upcomingWord?.text,
    );
  }
}
