import 'lyric_chord_marker_mapper.dart';

class LyricDisplayBlock {
  const LyricDisplayBlock({required this.index, required this.words});

  final int index;
  final List<LyricChordWord> words;

  double get start => words.first.word.start;
  double get end => words.last.word.end;
}

/// Turns timestamped words into short, phone-readable presentation blocks.
/// Source text and timestamps are never altered.
abstract final class LyricDisplayBlockGrouper {
  static const meaningfulGapSeconds = 0.8;
  static const maximumWords = 8;
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
