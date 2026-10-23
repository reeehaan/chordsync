import 'dart:io';
import 'dart:typed_data';

/// Reads the cover picture embedded in an MP3's ID3v2 tag, if it has one.
abstract final class EmbeddedCoverArt {
  /// Tags larger than this are not read; real ones with art are a few MB.
  static const _maximumTagBytes = 12 * 1024 * 1024;

  static Future<Uint8List?> read(File file) async {
    RandomAccessFile? handle;
    try {
      handle = await file.open();
      final header = await handle.read(10);
      final size = _tagSize(header);
      if (size == null || size > _maximumTagBytes) return null;
      await handle.setPosition(0);
      return parse(Uint8List.fromList(await handle.read(size + 10)));
    } on Object {
      return null;
    } finally {
      await handle?.close();
    }
  }

  /// The tag's body size, or null if [header] is not an ID3v2 header.
  static int? _tagSize(Uint8List header) {
    if (header.length < 10 ||
        header[0] != 0x49 || // I
        header[1] != 0x44 || // D
        header[2] != 0x33) {
      // 3
      return null;
    }
    return _syncSafe(header, 6);
  }

  static int _syncSafe(Uint8List bytes, int offset) =>
      (bytes[offset] << 21) |
      (bytes[offset + 1] << 14) |
      (bytes[offset + 2] << 7) |
      bytes[offset + 3];

  static int _bigEndian(Uint8List bytes, int offset) =>
      (bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3];

  /// The picture in an ID3v2.3 or v2.4 [tag] (header included), or null.
  static Uint8List? parse(Uint8List tag) {
    final size = _tagSize(tag);
    if (size == null) return null;
    final version = tag[3];
    if (version != 3 && version != 4) return null;
    final end = (size + 10).clamp(0, tag.length);
    var offset = 10;
    // An extended header, when present, comes before the first frame.
    if (tag[5] & 0x40 != 0 && offset + 4 <= end) {
      offset += version == 4
          ? _syncSafe(tag, offset)
          : _bigEndian(tag, offset) + 4;
    }
    while (offset + 10 <= end) {
      if (tag[offset] == 0) break; // padding
      final id = String.fromCharCodes(tag.sublist(offset, offset + 4));
      final frameSize = version == 4
          ? _syncSafe(tag, offset + 4)
          : _bigEndian(tag, offset + 4);
      final start = offset + 10;
      if (frameSize <= 0 || start + frameSize > end) break;
      if (id == 'APIC') {
        return _pictureIn(tag.sublist(start, start + frameSize));
      }
      offset = start + frameSize;
    }
    return null;
  }

  /// The image bytes of an APIC frame body: encoding, MIME type, picture
  /// type, description, then the picture.
  static Uint8List? _pictureIn(Uint8List frame) {
    if (frame.length < 4) return null;
    final encoding = frame[0];
    var index = 1;
    while (index < frame.length && frame[index] != 0) {
      index++; // MIME type, ends at a zero byte
    }
    index += 2; // the zero, then the picture-type byte
    // The description ends at a zero byte, or a pair of them in UTF-16.
    final wide = encoding == 1 || encoding == 2;
    while (index < frame.length) {
      if (wide) {
        if (index + 1 < frame.length &&
            frame[index] == 0 &&
            frame[index + 1] == 0) {
          index += 2;
          break;
        }
        index += 2;
      } else {
        if (frame[index] == 0) {
          index += 1;
          break;
        }
        index++;
      }
    }
    if (index >= frame.length) return null;
    final picture = frame.sublist(index);
    return _looksLikeImage(picture) ? picture : null;
  }

  static bool _looksLikeImage(Uint8List bytes) =>
      bytes.length > 4 &&
      ((bytes[0] == 0xFF && bytes[1] == 0xD8) || // JPEG
          (bytes[0] == 0x89 && bytes[1] == 0x50)); // PNG
}
