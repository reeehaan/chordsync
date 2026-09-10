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

  void setPosition(Duration position) {
    _position = position;
    final playbackTime =
        position.inMicroseconds / Duration.microsecondsPerSecond;
    _state = PlaybackLookup.playbackState(_timeline, playbackTime);
  }
}
