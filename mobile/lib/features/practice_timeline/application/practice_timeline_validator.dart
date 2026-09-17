import '../data/shared_timeline.dart';

class PracticeTimelineValidator {
  const PracticeTimelineValidator._();

  static void validate(SharedTimeline timeline) {
    if (timeline.schemaVersion != 1 ||
        !timeline.bpm.isFinite ||
        timeline.bpm <= 0 ||
        timeline.beatsPerBar <= 0 ||
        timeline.bars.isEmpty) {
      throw const FormatException('Timeline is not usable for practice.');
    }

    var previousBarEnd = 0.0;
    var previousBeatTime = -1.0;
    for (final bar in timeline.bars) {
      if (!bar.startTime.isFinite ||
          !bar.endTime.isFinite ||
          bar.startTime < 0 ||
          bar.endTime <= bar.startTime ||
          bar.startTime < previousBarEnd ||
          bar.beats.isEmpty) {
        throw const FormatException('Timeline bar structure is invalid.');
      }
      for (final beat in bar.beats) {
        if (!beat.time.isFinite ||
            beat.time < 0 ||
            beat.time < previousBeatTime ||
            beat.beatNumber < 1 ||
            beat.beatNumber > timeline.beatsPerBar) {
          throw const FormatException('Timeline beat structure is invalid.');
        }
        previousBeatTime = beat.time;
      }
      previousBarEnd = bar.endTime;
    }
  }
}
