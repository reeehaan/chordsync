enum PracticePlaybackStatus { loading, paused, playing, completed, error }

extension PracticePlaybackStatusLabel on PracticePlaybackStatus {
  String get label => switch (this) {
    PracticePlaybackStatus.loading => 'Loading',
    PracticePlaybackStatus.paused => 'Paused',
    PracticePlaybackStatus.playing => 'Playing',
    PracticePlaybackStatus.completed => 'Completed',
    PracticePlaybackStatus.error => 'Error',
  };
}
