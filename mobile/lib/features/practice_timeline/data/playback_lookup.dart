import 'playback_state.dart';
import 'shared_timeline.dart';

class PlaybackLookup {
  const PlaybackLookup._();

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

  static PlaybackState playbackState(
    SharedTimeline timeline,
    double playbackTime,
  ) {
    final beat = currentBeat(timeline, playbackTime);
    final word = activeLyricWord(timeline, playbackTime);

    return PlaybackState(
      playbackTime: playbackTime,
      chord: beat?.chord ?? 'N',
      beatNumber: beat?.beatNumber,
      isDownbeat: beat?.isDownbeat ?? false,
      lyricWord: word?.text,
    );
  }
}
