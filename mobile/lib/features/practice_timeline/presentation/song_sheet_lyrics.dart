import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../data/shared_timeline.dart';
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

  @override
  State<SongSheetLyrics> createState() => _SongSheetLyricsState();
}

class _SongSheetLyricsState extends State<SongSheetLyrics> {
  static const _blockExtent = 90.0;

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
    if (!identical(oldWidget.timeline, widget.timeline)) {
      _resolveBlocks();
    }
    final nextFocus = LyricDisplayBlockGrouper.focusedBlockIndex(
      _blocks,
      widget.playbackTime,
    );
    if (nextFocus == _focusedBlockIndex) return;
    _focusedBlockIndex = nextFocus;
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
      final target =
          (focused * _blockExtent -
                  (position.viewportDimension - _blockExtent) / 2)
              .clamp(0.0, position.maxScrollExtent);
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
      return const Center(
        child: Text('No lyrics detected', key: ValueKey('noLyricsFallback')),
      );
    }

    return Stack(
      children: [
        NotificationListener<UserScrollNotification>(
          onNotification: _handleUserScroll,
          child: ListView.builder(
            key: const ValueKey('lyricScrollView'),
            controller: _scrollController,
            physics: const ClampingScrollPhysics(),
            itemExtent: _blockExtent,
            padding: const EdgeInsets.fromLTRB(0, 12, 0, 40),
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
      opacity: isFocused ? 1 : 0.5,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 2),
          child: Wrap(
            alignment: WrapAlignment.center,
            spacing: 5,
            runSpacing: 9,
            crossAxisAlignment: WrapCrossAlignment.end,
            children: [
              for (final entry in block.words)
                _LyricChordWord(entry: entry, playbackTime: playbackTime),
            ],
          ),
        ),
      ),
    );
  }
}

class _LyricChordWord extends StatelessWidget {
  const _LyricChordWord({required this.entry, required this.playbackTime});

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
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 25,
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
                      Container(
                        key: ValueKey(
                          'inlineChord${entry.segmentIndex}_${entry.wordIndex}_$index',
                        ),
                        margin: const EdgeInsets.only(right: 4, bottom: 3),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 7,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: PracticeStageColors.surfaceRaised,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          entry.chordMarkers[index],
                          style: textTheme.labelSmall?.copyWith(
                            color: PracticeStageColors.textPrimary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                  ],
                ),
        ),
        AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
          decoration: BoxDecoration(
            color: isActive
                ? PracticeStageColors.activeWord
                : Colors.transparent,
            borderRadius: BorderRadius.circular(5),
          ),
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
              height: 1.24,
            ),
            child: Text(word.text, key: ValueKey('sheetWord${word.start}')),
          ),
        ),
      ],
    );
  }
}
