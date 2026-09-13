abstract final class PracticePlaybackSpeeds {
  static const double defaultSpeed = 1.0;
  static const List<double> supported = [0.5, 0.75, 1.0, 1.25, 1.5];

  static bool isSupported(double speed) => supported.contains(speed);

  static String label(double speed) => '${speed.toStringAsFixed(2)}x'
      .replaceFirst(RegExp(r'0+x$'), 'x')
      .replaceFirst('.x', '.0x');
}
