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
      final documents = await documentsDirectory();
      final sessions = <AnalyzedPracticeSession>[];
      for (final value in decoded) {
        try {
          final session = await _sessionFromJson(
            value as Map<String, dynamic>,
            documents,
          );
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
    final documents = await documentsDirectory();
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(
      jsonEncode(
        sessions.map((session) => _sessionToJson(session, documents)).toList(),
      ),
      flush: true,
    );
    await temporary.rename(file.path);
  }

  /// A path saved inside the documents folder is kept relative to it: iOS moves
  /// the app's folder when the app is updated, so an absolute path goes stale.
  static String _relativeToDocuments(String path, String documents) =>
      p.isWithin(documents, path) ? p.relative(path, from: documents) : path;

  /// Where a saved audio path points now. Relative paths and absolute paths
  /// saved by older versions are both mapped into the current documents
  /// folder.
  static Future<String> resolveAudioPath(
    String stored,
    String documents,
  ) async {
    if (p.isRelative(stored)) {
      final joined = p.normalize(p.join(documents, stored));
      // A saved path must stay inside the documents folder.
      return p.isWithin(documents, joined) ? joined : stored;
    }
    if (await File(stored).exists()) return stored;
    final marker = '${p.separator}Documents${p.separator}';
    final index = stored.lastIndexOf(marker);
    if (index < 0) return stored;
    return p.join(documents, stored.substring(index + marker.length));
  }

  Future<AnalyzedPracticeSession> _sessionFromJson(
    Map<String, dynamic> json,
    Directory documents,
  ) async {
    return AnalyzedPracticeSession(
      title: json['title'] as String,
      audioFile: File(
        await resolveAudioPath(json['audio_path'] as String, documents.path),
      ),
      job: AnalysisJob.fromJson(json['job'] as Map<String, dynamic>),
      timeline: SharedTimeline.fromJson(
        json['timeline'] as Map<String, dynamic>,
      ),
      cleanChords: json['clean_chords'] as bool? ?? true,
    );
  }

  Map<String, dynamic> _sessionToJson(
    AnalyzedPracticeSession session,
    Directory documents,
  ) => {
    'title': session.title,
    'audio_path': _relativeToDocuments(session.audioFile.path, documents.path),
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
    'clean_chords': session.cleanChords,
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
