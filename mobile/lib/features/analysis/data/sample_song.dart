import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../../practice_timeline/data/shared_timeline.dart';
import '../application/analyzed_practice_session.dart';
import 'analysis_job.dart';
import 'analyzed_session_library.dart';

/// A short built-in song that plays through the 7, maj7, m7, sus2 and sus4
/// chord shapes, so they can be tried on a phone without analysing anything.
/// It is only offered in builds that ask for it, and it is never saved.
class SampleSong {
  SampleSong({
    this.documentsDirectory = getApplicationDocumentsDirectory,
    AssetBundle? bundle,
  }) : _bundle = bundle ?? rootBundle;

  static const jobId = 'sample-extended-chords';
  static const title = 'Extended chords sample';
  static const audioAsset = 'assets/practice_audio/extended_chords_sample.wav';
  static const timelineAsset =
      'assets/practice_timeline/extended_chords_sample.json';

  final Future<Directory> Function() documentsDirectory;
  final AssetBundle _bundle;

  Future<AnalyzedPracticeSession> session() async {
    final timeline = SharedTimeline.fromJson(
      jsonDecode(await _bundle.loadString(timelineAsset))
          as Map<String, dynamic>,
    );
    final documents = await documentsDirectory();
    final directory = Directory(p.join(documents.path, 'imported_audio'));
    await directory.create(recursive: true);
    final audio = File(p.join(directory.path, 'sample-extended-chords.wav'));
    final bytes = (await _bundle.load(audioAsset)).buffer.asUint8List();
    if (!await audio.exists() || await audio.length() != bytes.length) {
      await audio.writeAsBytes(bytes, flush: true);
    }
    final now = DateTime.now().toUtc();
    return AnalyzedPracticeSession(
      title: title,
      audioFile: audio,
      job: AnalysisJob(
        jobId: jobId,
        status: AnalysisJobStatus.completed,
        createdAt: now,
        updatedAt: now,
        error: null,
        resultAvailable: true,
      ),
      timeline: timeline,
    );
  }
}

/// The saved songs with the sample song at the top. The sample is added when
/// the list is read and is never written to the saved songs.
class SampleAugmentedLibrary implements AnalyzedSessionLibrary {
  SampleAugmentedLibrary(this._saved, this._sample);

  final AnalyzedSessionLibrary _saved;
  final SampleSong _sample;

  @override
  Future<List<AnalyzedPracticeSession>> load() async {
    final saved = await _saved.load();
    try {
      return [await _sample.session(), ...saved];
    } on Object {
      return saved; // a broken sample must never hide the real songs
    }
  }

  @override
  Future<void> save(AnalyzedPracticeSession session) => _saved.save(session);
}
