import 'lyric_chord_marker_mapper.dart';

class LyricDisplayBlock {
  LyricDisplayBlock({required this.index, required this.words})
    : highlightsWholeLine = LyricScript.isCjk(
        words.map((entry) => entry.word.text).join(),
      );

  final int index;
  final List<LyricChordWord> words;

  /// Chinese, Japanese and Korean lyrics are lit a whole line at a time:
  /// their words are not separated by spaces, so a single word is too small
  /// to follow. Every other language is lit word by word.
  final bool highlightsWholeLine;

  double get start => words.first.word.start;
  double get end => words.last.word.end;
}

abstract final class LyricScript {
  // Han, kana, half-width kana and Hangul (BMP ranges only).
  static final _cjk = RegExp(
    r'[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF\u31F0-\u31FF'
    r'\uFF66-\uFF9F\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF]',
  );
  static final _letter = RegExp(r'\p{L}', unicode: true);

  /// True when at least half of the letters are Han, kana or Hangul, so a
  /// name or loanword in an English line does not switch the whole line.
  static bool isCjk(String text) {
    final cjk = _cjk.allMatches(text).length;
    if (cjk == 0) return false;
    return cjk * 2 >= _letter.allMatches(text).length;
  }
}

/// Turns timestamped words into short, phone-readable presentation blocks.
/// Source text and timestamps are never altered.
abstract final class LyricDisplayBlockGrouper {
  static const meaningfulGapSeconds = 0.8;
  static const maximumWords = 7;
  static const maximumCharacters = 38;

  static List<LyricDisplayBlock> group(List<LyricChordWord> words) {
    if (words.isEmpty) return const [];

    final blocks = <LyricDisplayBlock>[];
    var current = <LyricChordWord>[];
    var characterCount = 0;

    void finishBlock() {
      if (current.isEmpty) return;
      blocks.add(
        LyricDisplayBlock(
          index: blocks.length,
          words: List.unmodifiable(current),
        ),
      );
      current = [];
      characterCount = 0;
    }

    for (var index = 0; index < words.length; index++) {
      final entry = words[index];
      final addedCharacters =
          entry.word.text.length + (current.isEmpty ? 0 : 1);
      if (current.isNotEmpty &&
          (current.length >= maximumWords ||
              characterCount + addedCharacters > maximumCharacters)) {
        finishBlock();
      }

      current.add(entry);
      characterCount += entry.word.text.length + (current.length == 1 ? 0 : 1);

      final next = index + 1 < words.length ? words[index + 1] : null;
      final punctuationBoundary = RegExp(r'[.!?;:]$').hasMatch(entry.word.text);
      final commaBoundary =
          current.length >= 4 && entry.word.text.endsWith(',');
      final timingBoundary =
          next != null &&
          next.word.start - entry.word.end >= meaningfulGapSeconds;

      if (next == null ||
          punctuationBoundary ||
          commaBoundary ||
          timingBoundary) {
        finishBlock();
      }
    }

    return List.unmodifiable(blocks);
  }

  static int? focusedBlockIndex(
    List<LyricDisplayBlock> blocks,
    double playbackTime,
  ) {
    if (blocks.isEmpty) return null;

    for (final block in blocks) {
      for (final entry in block.words) {
        if (entry.word.start <= playbackTime && playbackTime < entry.word.end) {
          return block.index;
        }
      }
    }

    var focused = 0;
    for (final block in blocks) {
      if (block.start <= playbackTime) {
        focused = block.index;
      } else {
        break;
      }
    }
    return focused;
  }
}
