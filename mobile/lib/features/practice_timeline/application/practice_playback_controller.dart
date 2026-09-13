import '../data/playback_lookup.dart';
import '../data/playback_state.dart';
import '../data/shared_timeline.dart';

class PracticePlaybackController {
  PracticePlaybackController(this._timeline)
    : _state = PlaybackLookup.playbackState(_timeline, 0);

  final SharedTimeline _timeline;
  Duration _position = Duration.zero;
  PlaybackState _state;

  Duration get position => _position;
  PlaybackState get state => _state;

  Duration? previousBarStart(Duration position) {
    return _barStartDuration(
      PlaybackLookup.previousBarStart(_timeline, _seconds(position)),
    );
  }

  Duration? nextBarStart(Duration position) {
    return _barStartDuration(
      PlaybackLookup.nextBarStart(_timeline, _seconds(position)),
    );
  }

  void setPosition(Duration position) {
    _position = position;
    final playbackTime = _seconds(position);
    _state = PlaybackLookup.playbackState(_timeline, playbackTime);
  }

  double _seconds(Duration position) {
    return position.inMicroseconds / Duration.microsecondsPerSecond;
  }

  Duration? _barStartDuration(double? seconds) {
    if (seconds == null) return null;
    return Duration(
      microseconds: (seconds * Duration.microsecondsPerSecond).round(),
    );
  }
}
