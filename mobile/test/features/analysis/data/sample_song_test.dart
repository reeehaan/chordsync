import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
import 'package:chordsync/features/analysis/data/sample_song.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/presentation/chord_diagram.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _BrokenBundle extends CachingAssetBundle {
  @override
  Future<ByteData> load(String key) async => throw StateError('no asset');
}

class _FakeLibrary implements AnalyzedSessionLibrary {
  final saved = <AnalyzedPracticeSession>[];
  List<AnalyzedPracticeSession> existing = const [];

  @override
  Future<List<AnalyzedPracticeSession>> load() async => existing;

  @override
  Future<void> save(AnalyzedPracticeSession session) async =>
      saved.add(session);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory documents;

  setUp(() {
    documents = Directory.systemTemp.createTempSync('chordsync-sample-');
  });
  tearDown(() => documents.deleteSync(recursive: true));

  SampleSong sample() => SampleSong(documentsDirectory: () async => documents);

  test('the sample plays all 84 chords the app can draw', () async {
    final timeline = SharedTimeline.fromJson(
      jsonDecode(await rootBundle.loadString(SampleSong.timelineAsset))
          as Map<String, dynamic>,
    );
    final played = [
      for (final bar in timeline.bars)
        for (final beat in bar.beats) beat.chord,
    ];
    const roots = [
      'C',
      'C#',
      'D',
      'D#',
      'E',
      'F',
      'F#',
      'G',
      'G#',
      'A',
      'A#',
      'B',
    ];
    const suffixes = ['', 'm', '7', 'maj7', 'm7', 'sus2', 'sus4'];

    for (final root in roots) {
      for (final suffix in suffixes) {
        expect(played, contains('$root$suffix'), reason: '$root$suffix');
      }
    }
    // Each is held for a couple of beats, in the order: plain, then each type.
    expect(played.toSet().length, 84);
  });

  test('every chord in the sample has a drawn shape', () async {
    final timeline = SharedTimeline.fromJson(
      jsonDecode(await rootBundle.loadString(SampleSong.timelineAsset))
          as Map<String, dynamic>,
    );
    final chords = {
      for (final bar in timeline.bars)
        for (final beat in bar.beats) beat.chord,
    };

    expect(chords.length, 84);
    for (final chord in chords) {
      expect(ChordDiagram.fretsFor(chord), isNotNull, reason: chord);
    }
    // It really does cover the five new chord types.
    for (final suffix in ['7', 'maj7', 'm7', 'sus2', 'sus4']) {
      expect(
        chords.any((chord) => chord.endsWith(suffix)),
        isTrue,
        reason: 'no $suffix chord',
      );
    }
  });

  test('the recording is long enough for the whole timeline', () async {
    final timeline = SharedTimeline.fromJson(
      jsonDecode(await rootBundle.loadString(SampleSong.timelineAsset))
          as Map<String, dynamic>,
    );
    final bytes = (await rootBundle.load(
      SampleSong.audioAsset,
    )).buffer.asUint8List();
    final header = ByteData.sublistView(bytes);
    final rate = header.getUint32(24, Endian.little);
    final seconds = (bytes.length - 44) / (rate * 2);

    expect(String.fromCharCodes(bytes.sublist(0, 4)), 'RIFF');
    expect(seconds, greaterThanOrEqualTo(timeline.endTime));
  });

  test('builds a completed session with the audio written to disk', () async {
    final session = await sample().session();

    expect(session.title, SampleSong.title);
    expect(session.job.jobId, SampleSong.jobId);
    expect(session.audioFile.existsSync(), isTrue);
    expect(
      session.audioFile.path,
      '${documents.path}/imported_audio/sample-extended-chords.wav',
    );
    expect(session.timeline.bars, isNotEmpty);
    // Asking again does not rewrite the file.
    final modified = session.audioFile.lastModifiedSync();
    await sample().session();
    expect(session.audioFile.lastModifiedSync(), modified);
  });

  test('the sample comes first and is never saved', () async {
    final saved = _FakeLibrary();
    final library = SampleAugmentedLibrary(saved, sample());
    saved.existing = const [];

    final songs = await library.load();
    expect(songs.map((s) => s.job.jobId), [SampleSong.jobId]);

    final other = await sample().session();
    await library.save(other);
    // Saving passes straight through to the real library.
    expect(saved.saved, [other]);
  });

  test('a broken sample never hides the real songs', () async {
    final saved = _FakeLibrary();
    final real = await sample().session();
    saved.existing = [real];
    final library = SampleAugmentedLibrary(
      saved,
      SampleSong(
        documentsDirectory: () async => documents,
        bundle: _BrokenBundle(),
      ),
    );

    expect(await library.load(), [real]);
  });
}
