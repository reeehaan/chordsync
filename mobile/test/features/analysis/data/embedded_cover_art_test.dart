import 'dart:io';
import 'dart:typed_data';

import 'package:chordsync/features/analysis/data/embedded_cover_art.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Smallest bytes that pass for a JPEG here.
  final jpeg = Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, 1, 2, 3, 4, 5]);

  Uint8List frame(String id, List<int> body, {bool syncSafe = false}) {
    final size = body.length;
    final sizeBytes = syncSafe
        ? [
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
          ]
        : [
            (size >> 24) & 0xFF,
            (size >> 16) & 0xFF,
            (size >> 8) & 0xFF,
            size & 0xFF,
          ];
    return Uint8List.fromList([...id.codeUnits, ...sizeBytes, 0, 0, ...body]);
  }

  Uint8List tag(int version, List<Uint8List> frames, {int padding = 0}) {
    final body = [for (final f in frames) ...f, ...List.filled(padding, 0)];
    final size = body.length;
    return Uint8List.fromList([
      0x49,
      0x44,
      0x33,
      version,
      0,
      0,
      (size >> 21) & 0x7F,
      (size >> 14) & 0x7F,
      (size >> 7) & 0x7F,
      size & 0x7F,
      ...body,
    ]);
  }

  // encoding, "image/jpeg\0", picture type, description + terminator, picture
  List<int> apic({int encoding = 0, String description = ''}) => [
    encoding,
    ...'image/jpeg'.codeUnits,
    0,
    3,
    ...description.codeUnits,
    ...(encoding == 1 ? [0, 0] : [0]),
    ...jpeg,
  ];

  test('finds the picture in an ID3v2.3 tag after other frames', () {
    final result = EmbeddedCoverArt.parse(
      tag(3, [
        frame('TIT2', [0, 65, 66]),
        frame('APIC', apic()),
      ], padding: 8),
    );
    expect(result, jpeg);
  });

  test('finds the picture in an ID3v2.4 tag with sync-safe frame sizes', () {
    final result = EmbeddedCoverArt.parse(
      tag(4, [frame('APIC', apic(description: 'Front'), syncSafe: true)]),
    );
    expect(result, jpeg);
  });

  test('reads past a UTF-16 description', () {
    final result = EmbeddedCoverArt.parse(
      tag(3, [frame('APIC', apic(encoding: 1, description: ''))]),
    );
    expect(result, jpeg);
  });

  test('returns null when there is no picture or no tag', () {
    expect(
      EmbeddedCoverArt.parse(
        tag(3, [
          frame('TIT2', [0, 65]),
        ]),
      ),
      isNull,
    );
    expect(EmbeddedCoverArt.parse(Uint8List.fromList([1, 2, 3])), isNull);
    expect(
      EmbeddedCoverArt.parse(
        tag(3, [
          frame('APIC', [0, ...'image/jpeg'.codeUnits, 0, 3, 0, 9, 9, 9, 9, 9]),
        ]),
      ),
      isNull, // the bytes are not an image
    );
  });

  test('reads a file, and gives null for a file with no tag', () async {
    final dir = Directory.systemTemp.createTempSync('cover-test-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final withArt = File('${dir.path}/a.mp3')
      ..writeAsBytesSync([
        ...tag(3, [frame('APIC', apic())]),
        0xFF,
        0xFB,
      ]);
    final without = File('${dir.path}/b.mp3')
      ..writeAsBytesSync([0xFF, 0xFB, 1]);

    expect(await EmbeddedCoverArt.read(withArt), jpeg);
    expect(await EmbeddedCoverArt.read(without), isNull);
    expect(
      await EmbeddedCoverArt.read(File('${dir.path}/missing.mp3')),
      isNull,
    );
  });
}
