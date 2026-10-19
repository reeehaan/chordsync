import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../data/shared_timeline.dart';
import 'chord_chart.dart';
import 'lyric_chord_marker_mapper.dart';
import 'lyric_display_block.dart';
import 'practice_stage_colors.dart';

class SongSheetLyrics extends StatefulWidget {
  const SongSheetLyrics({
    super.key,
    required this.timeline,
    required this.playbackTime,
  });

  final SharedTimeline timeline;
  final double playbackTime;

  /// Chord chip lane, reserved on every word so words with and without a
  /// chord still sit on one shared baseline.
  static const chordLaneHeight = 26.0;
  static const wordLineHeight = 30.0;

  /// Height of one chord-plus-word run.
  static const runExtent = chordLaneHeight + wordLineHeight;

  /// Breathing room added above and below each line's content.
  static const lineGap = 18.0;

  /// Uniform row height. Every lyric line reserves the same vertical space so
  /// the gaps between lines — and above the first and below the last — stay
  /// visually identical while the sheet scrolls.
  static const blockExtent = runExtent + lineGap;

  @override
  State<SongSheetLyrics> createState() => _SongSheetLyricsState();
}

class _SongSheetLyricsState extends State<SongSheetLyrics> {
  final ScrollController _scrollController = ScrollController();
  late List<LyricDisplayBlock> _blocks;
  int? _focusedBlockIndex;
  bool _autoFollow = true;

  @override
  void initState() {
    super.initState();
    _resolveBlocks();
    _scheduleFollow(jump: true);
  }

  @override
  void didUpdateWidget(covariant SongSheetLyrics oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Compare against the line the sheet last followed *before* regrouping:
    // with a capo set the timeline object changes on every build, and
    // regrouping refreshes the focus, which would hide every change.
    final previousFocus = _focusedBlockIndex;
    if (!identical(oldWidget.timeline, widget.timeline)) {
      _resolveBlocks();
    }
    final nextFocus = LyricDisplayBlockGrouper.focusedBlockIndex(
      _blocks,
      widget.playbackTime,
    );
    _focusedBlockIndex = nextFocus;
    if (nextFocus == previousFocus) return;
    if (_autoFollow) _scheduleFollow();
  }

  void _resolveBlocks() {
    _blocks = LyricDisplayBlockGrouper.group(
      LyricChordMarkerMapper.map(widget.timeline),
    );
    _focusedBlockIndex = LyricDisplayBlockGrouper.focusedBlockIndex(
      _blocks,
      widget.playbackTime,
    );
  }

  void _scheduleFollow({bool jump = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_autoFollow || !_scrollController.hasClients) return;
      final focused = _focusedBlockIndex;
      if (focused == null) return;
      final position = _scrollController.position;
      const extent = SongSheetLyrics.blockExtent;
      final target =
          (focused * extent - (position.viewportDimension - extent) / 2).clamp(
            0.0,
            position.maxScrollExtent,
          );
      if (jump) {
        _scrollController.jumpTo(target);
      } else {
        _scrollController.animateTo(
          target,
          duration: const Duration(milliseconds: 320),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  bool _handleUserScroll(UserScrollNotification notification) {
    if (notification.direction != ScrollDirection.idle && _autoFollow) {
      setState(() => _autoFollow = false);
    }
    return false;
  }

  void _resumeFollow() {
    setState(() => _autoFollow = true);
    _scheduleFollow();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_blocks.isEmpty) {
      // No lyrics to put the chords over: show the chords bar by bar instead.
      return Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Column(
              children: [
                const Text(
                  'No lyrics detected',
                  key: ValueKey('noLyricsFallback'),
                ),
                Text(
                  'Showing the chords bar by bar.',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: PracticeStageColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: ChordChart(
              timeline: widget.timeline,
              playbackTime: widget.playbackTime,
            ),
          ),
        ],
      );
    }

    return Stack(
      children: [
        NotificationListener<UserScrollNotification>(
          onNotification: _handleUserScroll,
          child: ListView.builder(
            key: const ValueKey('lyricScrollView'),
            controller: _scrollController,
            // Always draggable, so browsing the sheet by hand still suspends
            // auto-follow even when a short song fits the viewport.
            physics: const AlwaysScrollableScrollPhysics(
              parent: ClampingScrollPhysics(),
            ),
            itemExtent: SongSheetLyrics.blockExtent,
            padding: const EdgeInsets.symmetric(vertical: 24),
            itemCount: _blocks.length,
            itemBuilder: (context, index) {
              final block = _blocks[index];
              return _FocusedLyricBlock(
                key: ValueKey('lyricBlock$index'),
                block: block,
                playbackTime: widget.playbackTime,
                isFocused: index == _focusedBlockIndex,
              );
            },
          ),
        ),
        if (!_autoFollow)
          Positioned(
            right: 12,
            bottom: 12,
            child: FilledButton.tonalIcon(
              key: const ValueKey('followLyricsButton'),
              onPressed: _resumeFollow,
              icon: const Icon(Icons.my_location, size: 17),
              label: const Text('Follow'),
            ),
          ),
      ],
    );
  }
}

class _FocusedLyricBlock extends StatelessWidget {
  const _FocusedLyricBlock({
    super.key,
    required this.block,
    required this.playbackTime,
    required this.isFocused,
  });

  final LyricDisplayBlock block;
  final double playbackTime;
  final bool isFocused;

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      key: isFocused ? const ValueKey('currentLyricBlock') : null,
      opacity: isFocused ? 1 : 0.42,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        // A lyric line always stays on one row: an over-long line is scaled
        // down a little rather than wrapping, which is what keeps every row
        // the same height and the spacing between rows even.
        child: FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Row(
            key: ValueKey('lyricRow${block.index}'),
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final entry in block.words)
                Padding(
                  padding: const EdgeInsets.only(right: 10),
                  child: _LyricChordWord(
                    key: ValueKey(
                      'lyricWordCell${entry.segmentIndex}_${entry.wordIndex}',
                    ),
                    entry: entry,
                    playbackTime: playbackTime,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One word sized to its own text, with its chord chip centred above it.
///
/// Words are never forced into equal-width columns: each takes exactly the
/// room its glyphs need, which is what keeps neighbouring words from
/// overlapping when one of them is long.
class _LyricChordWord extends StatelessWidget {
  const _LyricChordWord({
    super.key,
    required this.entry,
    required this.playbackTime,
  });

  final LyricChordWord entry;
  final double playbackTime;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final word = entry.word;
    final isActive = word.start <= playbackTime && playbackTime < word.end;
    final isPast = word.end <= playbackTime;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          height: SongSheetLyrics.chordLaneHeight,
          child: entry.chordMarkers.isEmpty
              ? null
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (
                      var index = 0;
                      index < entry.chordMarkers.length;
                      index++
                    )
                      _ChordChip(
                        key: ValueKey(
                          'inlineChord${entry.segmentIndex}_'
                          '${entry.wordIndex}_$index',
                        ),
                        label: entry.chordMarkers[index],
                        state: _chipState(
                          entry.chordSpans[index],
                          playbackTime,
                        ),
                      ),
                  ],
                ),
        ),
        SizedBox(
          height: SongSheetLyrics.wordLineHeight,
          child: Align(
            alignment: Alignment.bottomCenter,
            // Shrink-wrap horizontally: without this the cell would expand to
            // the full line width and push every other word onto its own row.
            widthFactor: 1,
            child: AnimatedDefaultTextStyle(
              key: ValueKey('sheetWordStyle${word.start}'),
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOutCubic,
              style: (textTheme.bodyLarge ?? const TextStyle()).copyWith(
                color: isActive
                    ? PracticeStageColors.amberBright
                    : isPast
                    ? PracticeStageColors.textFaint
                    : PracticeStageColors.textSecondary,
                fontWeight: isActive ? FontWeight.w800 : FontWeight.w500,
                fontSize: 19,
                height: 1.25,
              ),
              child: Text(
                word.text,
                key: ValueKey('sheetWord${word.start}'),
                maxLines: 1,
                softWrap: false,
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Where a chord is relative to the song, per the Golden Hour chip rules: one
/// pale-peach background, with state shown by border and text colour.
enum ChordChipState { upcoming, played, playing }

/// A chip follows its own chord's time span (so it lights up exactly when the
/// chord strip changes), not the word it sits above.
ChordChipState _chipState(ChordSpan span, double playbackTime) {
  if (span.isPlaying(playbackTime)) return ChordChipState.playing;
  return span.isUpcoming(playbackTime)
      ? ChordChipState.upcoming
      : ChordChipState.played;
}

class _ChordChip extends StatelessWidget {
  const _ChordChip({super.key, required this.label, required this.state});

  final String label;
  final ChordChipState state;

  @override
  Widget build(BuildContext context) {
    final playing = state == ChordChipState.playing;
    final textColor = switch (state) {
      ChordChipState.upcoming => ChordSyncColors.chipTextUpcoming,
      ChordChipState.played => ChordSyncColors.chipTextPlayed,
      ChordChipState.playing => ChordSyncColors.surface,
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: playing
            ? ChordSyncColors.currentChord
            : ChordSyncColors.inactiveChord,
        border: Border.all(
          color: state == ChordChipState.played
              ? ChordSyncColors.chipBorderPlayed
              : ChordSyncColors.chipBorderUpcoming,
          width: 1.2,
        ),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: textColor,
          fontWeight: FontWeight.w700,
          height: 1.2,
        ),
      ),
    );
  }
}
