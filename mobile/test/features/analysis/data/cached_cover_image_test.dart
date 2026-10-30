import 'dart:io';
import 'dart:typed_data';

import 'package:chordsync/features/analysis/data/cached_cover_image.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory folder;

  setUp(() {
    folder = Directory.systemTemp.createTempSync('covers');
    CachedCoverImage.cacheDirectory = () async => folder;
  });

  tearDown(() => folder.deleteSync(recursive: true));

  const key = CachedCoverImage(
    cacheKey: 'abcdef12-3456',
    url: 'https://bucket.example/c.jpg?sig=1',
  );

  testWidgets('a cover is fetched once, then read from the phone', (
    tester,
  ) async {
    await tester.runAsync(() async {
      var fetches = 0;
      Future<Uint8List> fetch(String url) async {
        fetches++;
        return Uint8List.fromList([1, 2, 3]);
      }

      final first = await CachedCoverImage.bytesFor(key, fetch: fetch);
      // A refresh signs a new link, but it is the same song.
      const relinked = CachedCoverImage(
        cacheKey: 'abcdef12-3456',
        url: 'https://bucket.example/c.jpg?sig=2',
      );
      final second = await CachedCoverImage.bytesFor(relinked, fetch: fetch);

      expect(first, [1, 2, 3]);
      expect(second, [1, 2, 3]);
      expect(fetches, 1);
    });
  });

  testWidgets('two cards asking at once share one fetch', (tester) async {
    await tester.runAsync(() async {
      var fetches = 0;
      Future<Uint8List> fetch(String url) async {
        fetches++;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return Uint8List.fromList([9]);
      }

      await Future.wait([
        CachedCoverImage.bytesFor(key, fetch: fetch),
        CachedCoverImage.bytesFor(key, fetch: fetch),
      ]);

      expect(fetches, 1);
    });
  });

  testWidgets('an unsafe key is fetched but never written to disk', (
    tester,
  ) async {
    await tester.runAsync(() async {
      const odd = CachedCoverImage(
        cacheKey: '../../x',
        url: 'https://b.example/c',
      );
      await CachedCoverImage.bytesFor(odd, fetch: (_) async => Uint8List(1));

      expect(folder.listSync(), isEmpty);
    });
  });
}
