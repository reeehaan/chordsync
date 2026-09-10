import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('loads the synthetic shared timeline asset', () async {
    final timeline = await SharedTimelineAssetLoader.load();

    expect(timeline.schemaVersion, 1);
    expect(timeline.bpm, 96);
    expect(timeline.beatsPerBar, 4);
    expect(timeline.beatSource, 'synthetic-grid');
    expect(timeline.lyricSource, 'synthetic-words');
    expect(timeline.bars, hasLength(2));
    expect(timeline.totalBeatCount, 8);
    expect(timeline.lyrics, hasLength(2));
    expect(timeline.totalLyricWordCount, 8);
  });
}
