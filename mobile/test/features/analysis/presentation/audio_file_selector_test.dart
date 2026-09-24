import 'dart:io';

import 'package:chordsync/features/analysis/presentation/audio_file_selector.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory sandbox;
  late Directory documents;

  setUp(() {
    sandbox = Directory.systemTemp.createTempSync('chordsync-import-test-');
    documents = Directory('${sandbox.path}/documents')..createSync();
  });

  tearDown(() => sandbox.deleteSync(recursive: true));

  test(
    'selected audio survives deletion of the picker hand-off file',
    () async {
      final source = File('${sandbox.path}/picker/song.WAV')
        ..createSync(recursive: true)
        ..writeAsBytesSync([1, 2, 3, 4]);
      final selector = NativeAudioFileSelector(
        pickFile: () async => source,
        documentsDirectory: () async => documents,
      );

      final selection = await selector.chooseAudio();
      expect(selection, isNotNull);
      expect(selection!.displayName, 'song.WAV');
      final imported = selection.file;
      expect(imported.path, isNot(source.path));
      expect(imported.path, startsWith('${documents.path}/imported_audio/'));
      expect(imported.path, endsWith('.wav'));

      await source.delete();
      expect(await imported.readAsBytes(), [1, 2, 3, 4]);
    },
  );

  test(
    'opaque names avoid collisions for the same original filename',
    () async {
      final first = File('${sandbox.path}/first/song.mp3')
        ..createSync(recursive: true)
        ..writeAsBytesSync([1]);
      final second = File('${sandbox.path}/second/song.mp3')
        ..createSync(recursive: true)
        ..writeAsBytesSync([2]);
      var source = first;
      final selector = NativeAudioFileSelector(
        pickFile: () async => source,
        documentsDirectory: () async => documents,
      );

      final firstImport = (await selector.chooseAudio())!.file;
      source = second;
      final secondImport = (await selector.chooseAudio())!.file;

      expect(firstImport.path, isNot(secondImport.path));
      expect(
        firstImport.uri.pathSegments.last,
        matches(RegExp(r'^[0-9a-f]{32}\.mp3$')),
      );
      expect(
        secondImport.uri.pathSegments.last,
        matches(RegExp(r'^[0-9a-f]{32}\.mp3$')),
      );
      expect(await firstImport.readAsBytes(), [1]);
      expect(await secondImport.readAsBytes(), [2]);
    },
  );

  test('rejects unsupported extensions without writing an import', () async {
    final source = File('${sandbox.path}/unsafe.json')
      ..writeAsStringSync('not audio');
    final selector = NativeAudioFileSelector(
      pickFile: () async => source,
      documentsDirectory: () async => documents,
    );

    await expectLater(
      selector.chooseAudio(),
      throwsA(isA<AudioFileSelectionException>()),
    );
    expect(Directory('${documents.path}/imported_audio').existsSync(), isFalse);
  });

  test('missing source and documents lookup failure expose no paths', () async {
    final missing = File('${sandbox.path}/private-source.wav');
    final selector = NativeAudioFileSelector(
      pickFile: () async => missing,
      documentsDirectory: () async => documents,
    );
    final unavailableDirectory = NativeAudioFileSelector(
      pickFile: () async => missing,
      documentsDirectory: () async => throw FileSystemException(
        'private storage failure',
        '${sandbox.path}/private-destination',
      ),
    );

    for (final candidate in [selector, unavailableDirectory]) {
      try {
        await candidate.chooseAudio();
        fail('Expected a safe audio import error');
      } on AudioFileSelectionException catch (error) {
        expect(
          error.toString(),
          'Could not import that audio file. Please try again.',
        );
        expect(error.toString(), isNot(contains(sandbox.path)));
      }
    }
  });

  test('partial copy is removed when writing fails', () async {
    final source = File('${sandbox.path}/song.m4a')
      ..writeAsBytesSync([1, 2, 3]);
    final selector = NativeAudioFileSelector(
      pickFile: () async => source,
      documentsDirectory: () async => documents,
      copyFile: (_, destination) async {
        await File(destination).writeAsBytes([1]);
        throw const FileSystemException('private copy failure');
      },
    );

    await expectLater(
      selector.chooseAudio(),
      throwsA(isA<AudioFileSelectionException>()),
    );
    expect(Directory('${documents.path}/imported_audio').listSync(), isEmpty);
  });

  test('empty copy is rejected and removed', () async {
    final source = File('${sandbox.path}/song.wav')
      ..writeAsBytesSync([1, 2, 3]);
    final selector = NativeAudioFileSelector(
      pickFile: () async => source,
      documentsDirectory: () async => documents,
      copyFile: (_, destination) async => File(destination)..createSync(),
    );

    await expectLater(
      selector.chooseAudio(),
      throwsA(isA<AudioFileSelectionException>()),
    );
    expect(Directory('${documents.path}/imported_audio').listSync(), isEmpty);
  });

  test('reselecting an app-owned import reuses the existing file', () async {
    var source = File('${sandbox.path}/song.wav')..writeAsBytesSync([1, 2]);
    final selector = NativeAudioFileSelector(
      pickFile: () async => source,
      documentsDirectory: () async => documents,
    );

    final imported = (await selector.chooseAudio())!.file;
    source = imported;
    final reselected = (await selector.chooseAudio())!.file;

    expect(reselected.path, imported.path);
    expect(
      Directory('${documents.path}/imported_audio').listSync(),
      hasLength(1),
    );
  });

  test('cancelled native pick returns null without creating storage', () async {
    final selector = NativeAudioFileSelector(
      pickFile: () async => null,
      documentsDirectory: () async => documents,
    );

    expect(await selector.chooseAudio(), isNull);
    expect(Directory('${documents.path}/imported_audio').existsSync(), isFalse);
  });
}
