import 'package:flutter/material.dart';

import 'chord_diagram.dart';
import 'practice_stage_colors.dart';

/// Horizontal strip of upcoming chord shapes with the sounding chord raised.
///
/// The strip only presents chords the playback state already resolved; it
/// never invents a voicing or reorders the progression.
class ChordDiagramStrip extends StatefulWidget {
  const ChordDiagramStrip({
    super.key,
    required this.previousChord,
    required this.currentChord,
    required this.nextChord,
    required this.progression,
    required this.chordProgress,
    required this.chordStart,
    this.showAllChords = false,
  });

  final String? previousChord;
  final String currentChord;
  final String? nextChord;
  final List<String> progression;
  final double? chordProgress;
  final double? chordStart;
  final bool showAllChords;

  static const compactHeight = 196.0;
  static const expandedHeight = 254.0;

  @override
  State<ChordDiagramStrip> createState() => _ChordDiagramStripState();
}

class _ChordDiagramStripState extends State<ChordDiagramStrip> {
  final ScrollController _scrollController = ScrollController();
  bool _isExpanded = false;

  @override
  void initState() {
    super.initState();
    _scheduleCenterActive();
  }

  @override
  void didUpdateWidget(covariant ChordDiagramStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentChord != widget.currentChord ||
        oldWidget.chordStart != widget.chordStart) {
      _scheduleCenterActive();
    }
  }

  void _scheduleCenterActive() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      final position = _scrollController.position;
      final entries = _entries();
      final activeIndex = entries.indexWhere((entry) => entry.isCurrent);
      if (activeIndex < 0) return;
      final cardExtent = _cardWidth + _cardGap;
      final target =
          (activeIndex * cardExtent -
                  (position.viewportDimension - _cardWidth) / 2)
              .clamp(0.0, position.maxScrollExtent);
      _scrollController.animateTo(
        target,
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutCubic,
      );
    });
  }

  double get _cardWidth => _isExpanded ? 128.0 : 104.0;
  double get _cardGap => 10.0;

  List<_StripEntry> _entries() {
    final upcoming = widget.progression
        .where((chord) => chord != widget.currentChord)
        .toList(growable: false);
    final following = <String>[
      ?widget.nextChord,
      ...upcoming.where((chord) => chord != widget.nextChord),
    ];
    final entries = [
      if (widget.previousChord case final previous?)
        _StripEntry(
          chord: previous,
          valueKey: const ValueKey('previousChordValue'),
        ),
      _StripEntry(
        chord: widget.currentChord,
        valueKey: const ValueKey('currentChordValue'),
        isCurrent: true,
      ),
      // The next slot always stays on screen; at the end of the song it
      // shows a dash rather than disappearing.
      _StripEntry(
        chord: following.isNotEmpty ? following[0] : '—',
        valueKey: const ValueKey('nextChordValue'),
        slotKey: const ValueKey('nextChordPreview'),
        isPlaceholder: following.isEmpty,
      ),
      if (following.length > 1)
        _StripEntry(
          chord: following[1],
          valueKey: const ValueKey('upcomingChordValue4'),
        ),
    ];
    if (!widget.showAllChords) return entries;

    final seen = <String>{widget.currentChord};
    final songChords = widget.progression
        .where((chord) => chord != 'N' && seen.add(chord))
        .toList(growable: false);
    return [
      entries.firstWhere((entry) => entry.isCurrent),
      for (var index = 0; index < songChords.length; index++)
        _StripEntry(
          chord: songChords[index],
          valueKey: index == 0
              ? const ValueKey('nextChordValue')
              : ValueKey('songChordValue${songChords[index]}'),
        ),
    ];
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final entries = _entries();
    return Semantics(
      container: true,
      label:
          'Previous chord ${widget.previousChord ?? 'none'}, current chord '
          '${widget.currentChord}, next chord ${widget.nextChord ?? 'none'}',
      child: SizedBox(
        key: const ValueKey('chordFocus'),
        height: _isExpanded
            ? ChordDiagramStrip.expandedHeight
            : ChordDiagramStrip.compactHeight,
        child: Stack(
          children: [
            // Every card is built, never lazily: the strip holds at most a
            // handful and the neighbouring shapes must stay readable even
            // while the active one is being centred.
            SingleChildScrollView(
              key: const ValueKey('chordDiagramStrip'),
              controller: _scrollController,
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var index = 0; index < entries.length; index++) ...[
                    if (index > 0) SizedBox(width: _cardGap),
                    _ChordCard(
                      key: entries[index].slotKey,
                      entry: entries[index],
                      width: _cardWidth,
                      chordProgress: entries[index].isCurrent
                          ? widget.chordProgress
                          : null,
                      chordStart: entries[index].isCurrent
                          ? widget.chordStart
                          : null,
                    ),
                  ],
                ],
              ),
            ),
            Positioned(
              top: 0,
              right: 12,
              child: _StripIconButton(
                isExpanded: _isExpanded,
                onPressed: () {
                  setState(() => _isExpanded = !_isExpanded);
                  _scheduleCenterActive();
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StripEntry {
  const _StripEntry({
    required this.chord,
    required this.valueKey,
    this.slotKey,
    this.isCurrent = false,
    this.isPlaceholder = false,
  });

  final String chord;
  final Key valueKey;
  final Key? slotKey;
  final bool isCurrent;
  final bool isPlaceholder;
}

class _ChordCard extends StatelessWidget {
  const _ChordCard({
    super.key,
    required this.entry,
    required this.width,
    required this.chordProgress,
    required this.chordStart,
  });

  final _StripEntry entry;
  final double width;
  final double? chordProgress;
  final double? chordStart;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final isCurrent = entry.isCurrent;
    final foreground = isCurrent
        ? PracticeStageColors.textPrimary
        : PracticeStageColors.textSecondary;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOutCubic,
      width: entry.isPlaceholder ? width * 0.6 : width,
      padding: const EdgeInsets.fromLTRB(6, 10, 6, 8),
      decoration: BoxDecoration(
        color: isCurrent
            ? PracticeStageColors.surfaceRaised
            : Colors.transparent,
        border: Border.all(
          color: isCurrent ? PracticeStageColors.border : Colors.transparent,
          width: 1.5,
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            entry.chord,
            key: entry.valueKey,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: isCurrent
                ? textTheme.titleLarge?.copyWith(
                    color: PracticeStageColors.amberBright,
                    fontWeight: FontWeight.w800,
                    height: 1.1,
                  )
                : textTheme.titleMedium?.copyWith(
                    color: PracticeStageColors.textSecondary,
                    fontWeight: FontWeight.w600,
                    height: 1.1,
                  ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: Center(
              child: entry.isPlaceholder
                  ? const SizedBox.shrink()
                  : FittedBox(
                      fit: BoxFit.contain,
                      child: ChordDiagram(
                        chord: entry.chord,
                        foregroundColor: foreground,
                        accentColor: foreground,
                      ),
                    ),
            ),
          ),
          if (isCurrent) ...[
            const SizedBox(height: 8),
            _ChordProgressBar(
              key: const ValueKey('chordProgressBar'),
              progress: chordProgress,
              chordStart: chordStart,
            ),
          ],
        ],
      ),
    );
  }
}

class _ChordProgressBar extends StatelessWidget {
  const _ChordProgressBar({
    super.key,
    required this.progress,
    required this.chordStart,
  });

  final double? progress;
  final double? chordStart;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: progress == null
          ? 'No chord duration to show'
          : 'Chord ${(progress! * 100).round()} percent played',
      child: TweenAnimationBuilder<double>(
        key: ValueKey(chordStart),
        tween: Tween(end: progress ?? 0),
        duration: const Duration(milliseconds: 180),
        curve: Curves.linear,
        builder: (context, value, child) => ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: value,
            minHeight: 5,
            backgroundColor: PracticeStageColors.border,
            valueColor: const AlwaysStoppedAnimation(
              PracticeStageColors.amberBright,
            ),
          ),
        ),
      ),
    );
  }
}

class _StripIconButton extends StatelessWidget {
  const _StripIconButton({required this.isExpanded, required this.onPressed});

  final bool isExpanded;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: PracticeStageColors.surfaceRaised,
      shape: const CircleBorder(),
      clipBehavior: Clip.antiAlias,
      child: IconButton(
        key: const ValueKey('expandDiagramsButton'),
        onPressed: onPressed,
        tooltip: isExpanded ? 'Shrink chord shapes' : 'Enlarge chord shapes',
        iconSize: 18,
        visualDensity: VisualDensity.compact,
        constraints: const BoxConstraints.tightFor(width: 36, height: 36),
        padding: EdgeInsets.zero,
        color: PracticeStageColors.textSecondary,
        icon: Icon(
          isExpanded
              ? Icons.close_fullscreen_rounded
              : Icons.open_in_full_rounded,
        ),
      ),
    );
  }
}
