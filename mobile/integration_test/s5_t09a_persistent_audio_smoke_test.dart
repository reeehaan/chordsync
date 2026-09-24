import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/presentation/audio_file_selector.dart';
import 'package:chordsync/features/practice_timeline/application/practice_audio_player.dart';
import 'package:chordsync/features/practice_timeline/application/practice_playback_status.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('persisted audio still plays after picker source disappears', (
    tester,
  ) async {
    await tester.runAsync(() async {
      final sourceDirectory = await Directory.systemTemp.createTemp(
        'chordsync-picker-handoff-',
      );
      final source = File(p.join(sourceDirectory.path, 'synthetic.WAV'));
      final data = await rootBundle.load(
        'assets/practice_audio/synthetic_practice.wav',
      );
      await source.writeAsBytes(data.buffer.asUint8List(), flush: true);

      final selector = NativeAudioFileSelector(pickFile: () async => source);
      final selection = (await selector.chooseAudio())!;
      expect(selection.displayName, 'synthetic.WAV');
      final imported = selection.file;
      final documents = await getApplicationDocumentsDirectory();
      expect(
        p.dirname(imported.path),
        p.join(documents.path, 'imported_audio'),
      );
      expect(
        p.basename(imported.path),
        matches(RegExp(r'^[0-9a-f]{32}\.wav$')),
      );

      await sourceDirectory.delete(recursive: true);
      expect(await imported.exists(), isTrue);

      final player = JustAudioPracticeAudioPlayer(filePath: imported.path);
      try {
        await player.load();
        expect(player.status, PracticePlaybackStatus.paused);
        unawaited(player.play());
        await Future<void>.delayed(const Duration(milliseconds: 700));
        expect(player.position, greaterThan(Duration.zero));
        await player.pause();
        expect(player.status, PracticePlaybackStatus.paused);
      } finally {
        await player.dispose();
        await imported.delete();
      }
    });
  }, timeout: const Timeout(Duration(minutes: 5)));
}
