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

  static TimelineEvent? nextBeat(SharedTimeline timeline, double playbackTime) {
    for (final bar in timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.time > playbackTime) return beat;
      }
    }
    return null;
  }

  static PracticeRegion? activePracticeRegion(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    for (final region in timeline.practiceRegions) {
      if (region.start <= playbackTime && playbackTime < region.end) {
        return region;
      }
    }
    return null;
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

  /// Returns when the chord active at [playbackTime] first started playing,
  /// so callers can measure how far through that chord's span playback is.
  static double? currentChordStart(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    double? runStart;
    String? runChord;
    double? result;

    for (final bar in timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.chord != runChord) {
          runChord = beat.chord;
          runStart = beat.time;
        }
        if (beat.time <= playbackTime) {
          result = runStart;
        } else {
          return result;
        }
      }
    }

    return result;
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

  /// Returns the chord run immediately before the chord active at
  /// [playbackTime]. Repeated beat labels inside the same run are ignored.
  static String? previousChord(SharedTimeline timeline, double playbackTime) {
    String? activeRun;
    String? previousRun;
    var hasActiveBeat = false;

    for (final bar in timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.time > playbackTime) return hasActiveBeat ? previousRun : null;
        hasActiveBeat = true;
        if (beat.chord != activeRun) {
          previousRun = activeRun;
          activeRun = beat.chord;
        }
      }
    }

    return hasActiveBeat ? previousRun : null;
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
    final followingBeat = nextBeat(timeline, playbackTime);
    final practiceRegion = activePracticeRegion(timeline, playbackTime);
    final activeWord = activeLyricWord(timeline, playbackTime);
    final upcomingChord = nextChord(timeline, playbackTime);
    final previousWord = previousLyricWord(timeline, playbackTime);
    final upcomingWord = nextLyricWord(timeline, playbackTime);
    final chordStart = currentChordStart(timeline, playbackTime);
    final chordEnd = chordStart == null
        ? null
        : (upcomingChord?.time ?? timeline.endTime);

    return PlaybackState(
      playbackTime: playbackTime,
      chord: beat?.chord ?? 'N',
      currentBarNumber: bar?.barNumber,
      beatNumber: beat?.beatNumber,
      beatsPerBar: timeline.beatsPerBar,
      isDownbeat: beat?.isDownbeat ?? false,
      chordProgression: chordProgression(timeline, playbackTime),
      previousChord: previousChord(timeline, playbackTime),
      nextChord: upcomingChord?.chord,
      currentChordStart: chordStart,
      currentChordEnd: chordEnd,
      previousLyricWord: previousWord?.text,
      lyricWord: activeWord?.text,
      nextLyricWord: upcomingWord?.text,
      isMusicOnly: practiceRegion?.mode == PracticeMode.musicOnly,
      musicOnlyStart: practiceRegion?.start,
      musicOnlyEnd: practiceRegion?.end,
      currentBeatStart: beat?.time,
      nextBeatStart:
          followingBeat?.time ??
          (beat == null ? null : beat.time + 60 / timeline.bpm),
    );
  }
}
