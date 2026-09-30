import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../../practice_timeline/data/shared_timeline.dart';
import '../application/analyzed_practice_session.dart';
import 'analysis_job.dart';

abstract interface class AnalyzedSessionLibrary {
  Future<List<AnalyzedPracticeSession>> load();

  Future<void> save(AnalyzedPracticeSession session);
}

class AnalyzedSessionLibraryException implements Exception {
  const AnalyzedSessionLibraryException();
}

class LocalAnalyzedSessionLibrary implements AnalyzedSessionLibrary {
  LocalAnalyzedSessionLibrary({
    this.documentsDirectory = getApplicationDocumentsDirectory,
  });

  final Future<Directory> Function() documentsDirectory;

  Future<File> get _indexFile async {
    final documents = await documentsDirectory();
    final directory = Directory(p.join(documents.path, 'analyzed_sessions'));
    await directory.create(recursive: true);
    return File(p.join(directory.path, 'sessions.json'));
  }

  @override
  Future<List<AnalyzedPracticeSession>> load() =>
      _load(tolerateCorruption: true);

  Future<List<AnalyzedPracticeSession>> _load({
    required bool tolerateCorruption,
  }) async {
    try {
      final file = await _indexFile;
      if (!await file.exists()) return const [];
      final decoded = jsonDecode(await file.readAsString()) as List<dynamic>;
      final sessions = <AnalyzedPracticeSession>[];
      for (final value in decoded) {
        try {
          final session = _sessionFromJson(value as Map<String, dynamic>);
          if (await session.audioFile.exists()) sessions.add(session);
        } on Object {
          // Preserve valid entries when one old local record is malformed.
        }
      }
      sessions.sort((a, b) => b.job.updatedAt.compareTo(a.job.updatedAt));
      return sessions;
    } on FileSystemException {
      rethrow;
    } on Object {
      if (tolerateCorruption) return const [];
      throw const AnalyzedSessionLibraryException();
    }
  }

  @override
  Future<void> save(AnalyzedPracticeSession session) async {
    final existing = await _load(tolerateCorruption: false);
    final sessions = [
      session,
      for (final item in existing)
        if (item.job.jobId != session.job.jobId) item,
    ];
    final file = await _indexFile;
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(
      jsonEncode(sessions.map(_sessionToJson).toList()),
      flush: true,
    );
    await temporary.rename(file.path);
  }

  AnalyzedPracticeSession _sessionFromJson(Map<String, dynamic> json) {
    return AnalyzedPracticeSession(
      title: json['title'] as String,
      audioFile: File(json['audio_path'] as String),
      job: AnalysisJob.fromJson(json['job'] as Map<String, dynamic>),
      timeline: SharedTimeline.fromJson(
        json['timeline'] as Map<String, dynamic>,
      ),
    );
  }

  Map<String, dynamic> _sessionToJson(AnalyzedPracticeSession session) => {
    'title': session.title,
    'audio_path': session.audioFile.path,
    'job': {
      'job_id': session.job.jobId,
      'status': session.job.status.name,
      'created_at': session.job.createdAt.toIso8601String(),
      'updated_at': session.job.updatedAt.toIso8601String(),
      'error': session.job.error == null
          ? null
          : {
              'code': session.job.error!.code,
              'message': session.job.error!.message,
            },
      'result_available': session.job.resultAvailable,
    },
    'timeline': _timelineToJson(session.timeline),
  };

  Map<String, dynamic> _timelineToJson(SharedTimeline timeline) => {
    'schema_version': timeline.schemaVersion,
    'bpm': timeline.bpm,
    'beats_per_bar': timeline.beatsPerBar,
    'beat_source': timeline.beatSource,
    'lyric_source': timeline.lyricSource,
    'bars': [
      for (final bar in timeline.bars)
        {
          'bar_number': bar.barNumber,
          'start_time': bar.startTime,
          'end_time': bar.endTime,
          'beats': [
            for (final beat in bar.beats)
              {
                'time': beat.time,
                'beat_number': beat.beatNumber,
                'is_downbeat': beat.isDownbeat,
                'chord': beat.chord,
              },
          ],
        },
    ],
    'lyrics': [
      for (final segment in timeline.lyrics)
        {
          'start': segment.start,
          'end': segment.end,
          'text': segment.text,
          'words': [
            for (final word in segment.words)
              {'start': word.start, 'end': word.end, 'text': word.text},
          ],
        },
    ],
    'practice_regions': [
      for (final region in timeline.practiceRegions)
        {
          'start': region.start,
          'end': region.end,
          'mode': switch (region.mode) {
            PracticeMode.musicOnly => 'music_only',
          },
        },
    ],
  };
}
