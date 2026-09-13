class PracticeLoop {
  PracticeLoop({required this.start, required this.end, required this.enabled})
    : assert(!start.isNegative),
      assert(end > start);

  final Duration start;
  final Duration end;
  final bool enabled;

  PracticeLoop copyWith({Duration? start, Duration? end, bool? enabled}) {
    return PracticeLoop(
      start: start ?? this.start,
      end: end ?? this.end,
      enabled: enabled ?? this.enabled,
    );
  }
}
