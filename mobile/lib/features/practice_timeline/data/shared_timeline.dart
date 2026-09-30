class SharedTimeline {
  const SharedTimeline({
    required this.schemaVersion,
    required this.bpm,
    required this.beatsPerBar,
    required this.beatSource,
    required this.lyricSource,
    required this.bars,
    required this.lyrics,
    this.practiceRegions = const [],
  });

  factory SharedTimeline.fromJson(Map<String, dynamic> json) {
    return SharedTimeline(
      schemaVersion: json['schema_version'] as int,
      bpm: (json['bpm'] as num).toDouble(),
      beatsPerBar: json['beats_per_bar'] as int,
      beatSource: json['beat_source'] as String,
      lyricSource: json['lyric_source'] as String,
      bars: (json['bars'] as List<dynamic>)
          .map((bar) => TimelineBar.fromJson(bar as Map<String, dynamic>))
          .toList(),
      lyrics: (json['lyrics'] as List<dynamic>)
          .map(
            (segment) => LyricSegment.fromJson(segment as Map<String, dynamic>),
          )
          .toList(),
      practiceRegions: (json['practice_regions'] as List<dynamic>? ?? const [])
          .map(
            (region) => PracticeRegion.fromJson(region as Map<String, dynamic>),
          )
          .toList(),
    );
  }

  final int schemaVersion;
  final double bpm;
  final int beatsPerBar;
  final String beatSource;
  final String lyricSource;
  final List<TimelineBar> bars;
  final List<LyricSegment> lyrics;
  final List<PracticeRegion> practiceRegions;

  int get totalBeatCount =>
      bars.fold(0, (total, bar) => total + bar.beats.length);

  int get totalLyricWordCount =>
      lyrics.fold(0, (total, segment) => total + segment.words.length);

  double get endTime => bars.fold(
    0,
    (latest, bar) => bar.endTime > latest ? bar.endTime : latest,
  );
}

enum PracticeMode { musicOnly }

class PracticeRegion {
  const PracticeRegion({
    required this.start,
    required this.end,
    required this.mode,
  });

  factory PracticeRegion.fromJson(Map<String, dynamic> json) {
    final mode = switch (json['mode']) {
      'music_only' => PracticeMode.musicOnly,
      final value => throw FormatException('Unsupported practice mode: $value'),
    };
    return PracticeRegion(
      start: (json['start'] as num).toDouble(),
      end: (json['end'] as num).toDouble(),
      mode: mode,
    );
  }

  final double start;
  final double end;
  final PracticeMode mode;
}

class TimelineBar {
  const TimelineBar({
    required this.barNumber,
    required this.startTime,
    required this.endTime,
    required this.beats,
  });

  factory TimelineBar.fromJson(Map<String, dynamic> json) {
    return TimelineBar(
      barNumber: json['bar_number'] as int,
      startTime: (json['start_time'] as num).toDouble(),
      endTime: (json['end_time'] as num).toDouble(),
      beats: (json['beats'] as List<dynamic>)
          .map((beat) => TimelineEvent.fromJson(beat as Map<String, dynamic>))
          .toList(),
    );
  }

  final int barNumber;
  final double startTime;
  final double endTime;
  final List<TimelineEvent> beats;
}

class TimelineEvent {
  const TimelineEvent({
    required this.time,
    required this.beatNumber,
    required this.isDownbeat,
    required this.chord,
  });

  factory TimelineEvent.fromJson(Map<String, dynamic> json) {
    return TimelineEvent(
      time: (json['time'] as num).toDouble(),
      beatNumber: json['beat_number'] as int,
      isDownbeat: json['is_downbeat'] as bool,
      chord: json['chord'] as String,
    );
  }

  final double time;
  final int beatNumber;
  final bool isDownbeat;
  final String chord;
}

class LyricSegment {
  const LyricSegment({
    required this.start,
    required this.end,
    required this.text,
    required this.words,
  });

  factory LyricSegment.fromJson(Map<String, dynamic> json) {
    return LyricSegment(
      start: (json['start'] as num).toDouble(),
      end: (json['end'] as num).toDouble(),
      text: json['text'] as String,
      words: (json['words'] as List<dynamic>)
          .map((word) => LyricWord.fromJson(word as Map<String, dynamic>))
          .toList(),
    );
  }

  final double start;
  final double end;
  final String text;
  final List<LyricWord> words;
}

class LyricWord {
  const LyricWord({required this.start, required this.end, required this.text});

  factory LyricWord.fromJson(Map<String, dynamic> json) {
    return LyricWord(
      start: (json['start'] as num).toDouble(),
      end: (json['end'] as num).toDouble(),
      text: json['text'] as String,
    );
  }

  final double start;
  final double end;
  final String text;
}
