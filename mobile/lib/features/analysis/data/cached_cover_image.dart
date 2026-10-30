import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// A song's cover, kept on this phone after the first time it is fetched.
///
/// The cover link the API sends is signed afresh on every list, so the link
/// itself changes each time and cannot be a cache key: the song's id is. Each
/// cover is then downloaded once, not again on every refresh or scroll, and a
/// song seen before shows its cover at once.
@immutable
class CachedCoverImage extends ImageProvider<CachedCoverImage> {
  const CachedCoverImage({required this.cacheKey, required this.url});

  /// What names the file on disk. Null means: fetch, but do not keep.
  final String? cacheKey;
  final String url;

  /// A cover older than this is fetched again, in case it was replaced.
  static const maxAge = Duration(days: 30);

  /// Covers are small; anything bigger is not one.
  static const maxBytes = 2 * 1024 * 1024;

  static final _safeKey = RegExp(r'^[A-Za-z0-9-]{8,64}$');
  static final _inFlight = <String, Future<Uint8List>>{};

  /// Where covers are kept. Replaceable so tests can use a temporary folder.
  @visibleForTesting
  static Future<Directory> Function() cacheDirectory = () async {
    final base = await getApplicationCacheDirectory();
    return Directory(p.join(base.path, 'covers'));
  };

  @override
  Future<CachedCoverImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(
    CachedCoverImage key,
    ImageDecoderCallback decode,
  ) {
    return MultiFrameImageStreamCompleter(codec: _load(key, decode), scale: 1);
  }

  Future<ui.Codec> _load(
    CachedCoverImage key,
    ImageDecoderCallback decode,
  ) async {
    final bytes = await bytesFor(key);
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    return decode(buffer);
  }

  /// The cover's bytes: from disk when kept, otherwise fetched (and kept).
  @visibleForTesting
  static Future<Uint8List> bytesFor(
    CachedCoverImage key, {
    Future<Uint8List> Function(String url)? fetch,
  }) {
    final name = key.cacheKey;
    if (name == null || !_safeKey.hasMatch(name)) {
      return (fetch ?? _fetch)(key.url);
    }
    // Several cards for one song ask at the same moment: fetch once.
    return _inFlight[name] ??= _readOrFetch(key, name, fetch ?? _fetch)
        .whenComplete(() {
          _inFlight.remove(name); // a block: returning it would wait on itself
        });
  }

  static Future<Uint8List> _readOrFetch(
    CachedCoverImage key,
    String name,
    Future<Uint8List> Function(String url) fetch,
  ) async {
    File? file;
    try {
      final directory = await cacheDirectory();
      file = File(p.join(directory.path, 'cover-$name'));
      if (await file.exists()) {
        final age = DateTime.now().difference(await file.lastModified());
        if (age < maxAge) return await file.readAsBytes();
      }
    } on Object {
      file = null; // no usable folder: still show the cover, just uncached
    }

    final bytes = await fetch(key.url);
    if (file != null) {
      try {
        await file.parent.create(recursive: true);
        final partial = File('${file.path}.part');
        await partial.writeAsBytes(bytes, flush: true);
        await partial.rename(file.path);
      } on Object {
        // Keeping it is a courtesy; the cover still shows.
      }
    }
    return bytes;
  }

  static Future<Uint8List> _fetch(String url) async {
    final uri = Uri.parse(url);
    if (uri.scheme != 'https') {
      throw const FormatException('A cover must come over https.');
    }
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 15);
    try {
      final request = await client.getUrl(uri);
      final response = await request.close();
      if (response.statusCode != 200) {
        throw HttpException('Cover request failed: ${response.statusCode}');
      }
      final builder = BytesBuilder(copy: false);
      await for (final chunk in response) {
        builder.add(chunk);
        if (builder.length > maxBytes) {
          throw const FormatException('The cover is larger than expected.');
        }
      }
      return builder.takeBytes();
    } finally {
      client.close(force: true);
    }
  }

  @override
  bool operator ==(Object other) =>
      other is CachedCoverImage &&
      other.cacheKey == cacheKey &&
      // Without a key the link is all there is to tell covers apart.
      (cacheKey != null || other.url == url);

  @override
  int get hashCode => cacheKey != null ? cacheKey.hashCode : url.hashCode;
}
