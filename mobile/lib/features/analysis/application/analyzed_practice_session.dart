import 'dart:io';

import '../../practice_timeline/data/shared_timeline.dart';
import '../data/analysis_job.dart';

class AnalyzedPracticeSession {
  const AnalyzedPracticeSession({
    required this.title,
    required this.job,
    required this.audioFile,
    required this.timeline,
  });

  final String title;
  final AnalysisJob job;
  final File audioFile;
  final SharedTimeline timeline;
}
