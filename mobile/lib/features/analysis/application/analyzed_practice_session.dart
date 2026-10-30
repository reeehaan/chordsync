import 'dart:io';

import '../../practice_timeline/data/shared_timeline.dart';
import '../data/analysis_job.dart';

class AnalyzedPracticeSession {
  AnalyzedPracticeSession({
    required this.title,
    required this.job,
    required this.audioFile,
    required this.timeline,
    this.cleanChords = false,
  });

  final String title;
  final AnalysisJob job;
  final File audioFile;

  /// The song as the analysis made it: this is what is saved.
  final SharedTimeline timeline;

  /// Whether practice shows the chords with the too-brief ones taken out.
  final bool cleanChords;

  /// This song with the clean-up switched on or off.
  AnalyzedPracticeSession withCleanChords(bool value) =>
      AnalyzedPracticeSession(
        title: title,
        job: job,
        audioFile: audioFile,
        timeline: timeline,
        cleanChords: value,
      );

  /// The song as practice shows it.
  late final SharedTimeline practiceTimeline = cleanChords
      ? timeline.withCleanChords()
      : timeline;
}
