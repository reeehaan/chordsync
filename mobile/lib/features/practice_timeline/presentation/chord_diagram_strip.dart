import 'package:flutter/material.dart';

import '../data/playback_state.dart';
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
    this.chordBeats = const [],
    this.playbackTime = 0,
  });

  final String? previousChord;
  final String currentChord;
  final String? nextChord;
  final List<String> progression;
  final double? chordProgress;
  final double? chordStart;
  final bool showAllChords;

  /// The beats of the current chord. When given (and few enough to read), the
  /// card shows one segment per beat instead of a plain progress bar.
  final List<ChordBeat> chordBeats;
  final double playbackTime;

  /// Longest chord shown as beat segments; a longer one keeps the bar.
  static const maximumBeatSegments = 8;

  static const compactHeight = 150.0;
  static const expandedHeight = 176.0;

  @override
  State<ChordDiagramStrip> createState() => _ChordDiagramStripState();
}

class _ChordDiagramStripState extends State<ChordDiagramStrip>
    with SingleTickerProviderStateMixin {
  final ScrollController _scrollController = ScrollController();
  // The song-wide row shown before playing has its own scroll position, so
  // the two rows can cross-fade without sharing one controller.
  final ScrollController _songScrollController = ScrollController();
  bool _isExpanded = false;

  /// Numbers the chords in the order they are played, so a card keeps its
  /// identity when the strip moves on: the "next" card becomes the current one
  /// instead of the cards being swapped in place.
  int _occurrence = 0;

  /// The glide to the next chord, from 0 (just changed) to 1 (settled).
  late final AnimationController _slide = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 360),
    value: 1,
  );

  /// The card that was "previous" before the last step, kept for the length
  /// of the glide so it fades out instead of vanishing.
  String? _departingChord;

  static const _glideCurve = Curves.easeOutCubic;

  @override
  void initState() {
    super.initState();
    _scheduleCenterActive();
  }

  @override
  void didUpdateWidget(covariant ChordDiagramStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentChord != widget.currentChord ||
        oldWidget.chordStart != widget.chordStart ||
        oldWidget.showAllChords != widget.showAllChords) {
      _trackChordChange(oldWidget);
      _scheduleCenterActive();
    }
  }

  /// Moves on one chord: the cards glide one place to the left. Any other
  /// change (a seek, a restart) gives every card a fresh identity instead.
  void _trackChordChange(ChordDiagramStrip old) {
    if (widget.showAllChords || old.showAllChords) return;
    final stepsForward =
        old.nextChord != null &&
        widget.currentChord == old.nextChord &&
        widget.previousChord == old.currentChord;
    if (!stepsForward) {
      _occurrence += 8;
      _departingChord = null;
      _slide.value = 1;
      return;
    }
    _occurrence++;
    // With no card before the old current one there is nothing to slide past;
    // the scroll view's own centring handles that first step.
    if (old.previousChord == null) return;
    _departingChord = old.previousChord;
    _slide.forward(from: 0).whenComplete(() {
      if (mounted) setState(() => _departingChord = null);
    });
  }

  void _scheduleCenterActive() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.showAllChords || !_scrollController.hasClients) {
        return;
      }
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
          slot: -1,
        ),
      _StripEntry(
        chord: widget.currentChord,
        valueKey: const ValueKey('currentChordValue'),
        isCurrent: true,
        slot: 0,
      ),
      // The next slot always stays on screen; at the end of the song it
      // shows a dash rather than disappearing.
      _StripEntry(
        chord: following.isNotEmpty ? following[0] : '—',
        valueKey: const ValueKey('nextChordValue'),
        isPlaceholder: following.isEmpty,
        slot: 1,
      ),
      if (following.length > 1)
        _StripEntry(
          chord: following[1],
          valueKey: const ValueKey('upcomingChordValue4'),
          slot: 2,
        ),
    ];
    if (!widget.showAllChords) return entries;
    return _songEntries();
  }

  /// Every chord of the song once, in the order it first plays, so the player
  /// can see all the shapes before pressing play. No chord is raised: that
  /// only begins once playback does.
  List<_StripEntry> _songEntries() {
    final seen = <String>{};
    final songChords = widget.progression
        .where((chord) => chord != 'N' && seen.add(chord))
        .toList(growable: false);
    return [
      for (var index = 0; index < songChords.length; index++)
        _StripEntry(
          chord: songChords[index],
          valueKey: switch (index) {
            0 => const ValueKey('currentChordValue'),
            1 => const ValueKey('nextChordValue'),
            _ => ValueKey('songChordValue${songChords[index]}'),
          },
          isStatic: true,
        ),
    ];
  }

  @override
  void dispose() {
    _slide.dispose();
    _scrollController.dispose();
    _songScrollController.dispose();
    super.dispose();
  }

  /// A card with the gap that follows it. Playing cards are keyed by which
  /// chord they are in the song, so each keeps its state (and animates)
  /// while its place in the row changes.
  Widget _slotCard(_StripEntry entry) {
    final slot = entry.slot;
    final key = slot == null
        ? ValueKey('songCard${entry.chord}')
        : ValueKey('chordCard${_occurrence + slot}');
    return Padding(
      key: key,
      padding: EdgeInsets.only(right: _cardGap),
      child: _ChordCard(
        entry: entry,
        width: _cardWidth,
        chordProgress: entry.isCurrent ? widget.chordProgress : null,
        chordStart: entry.isCurrent ? widget.chordStart : null,
        chordBeats: entry.isCurrent ? widget.chordBeats : const [],
        playbackTime: widget.playbackTime,
      ),
    );
  }

  /// The old previous card, fading out as the row glides past it.
  Widget _departingCard(String chord) {
    return Padding(
      key: ValueKey('chordCard${_occurrence - 2}'),
      padding: EdgeInsets.only(right: _cardGap),
      child: Opacity(
        opacity: 1 - _glideCurve.transform(_slide.value),
        child: _ChordCard(
          entry: _StripEntry(
            chord: chord,
            valueKey: const ValueKey('departingChordValue'),
          ),
          width: _cardWidth,
          chordProgress: null,
          chordStart: null,
          chordBeats: const [],
          playbackTime: widget.playbackTime,
        ),
      ),
    );
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
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 420),
              switchInCurve: Curves.easeOutCubic,
              switchOutCurve: Curves.easeInCubic,
              transitionBuilder: (child, animation) => FadeTransition(
                opacity: animation,
                child: SlideTransition(
                  position: Tween<Offset>(
                    begin: const Offset(0.04, 0),
                    end: Offset.zero,
                  ).animate(animation),
                  child: child,
                ),
              ),
              child: SingleChildScrollView(
                key: ValueKey(
                  widget.showAllChords
                      ? 'songChordDiagramStrip'
                      : 'playingChordDiagramStrip',
                ),
                controller: widget.showAllChords
                    ? _songScrollController
                    : _scrollController,
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                child: AnimatedBuilder(
                  animation: _slide,
                  builder: (context, child) {
                    // While gliding, the row starts where it was one card to
                    // the right and settles into place, taking the old
                    // previous card with it off the left edge.
                    final glide = _glideCurve.transform(_slide.value);
                    final shift = _departingChord == null
                        ? 0.0
                        : -(_cardWidth + _cardGap) * glide;
                    return Transform.translate(
                      offset: Offset(shift, 0),
                      child: child,
                    );
                  },
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_departingChord case final departing?)
                        _departingCard(departing),
                      for (final entry in entries) _slotCard(entry),
                    ],
                  ),
                ),
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
    this.slot,
    this.isCurrent = false,
    this.isPlaceholder = false,
    this.isStatic = false,
  });

  final String chord;
  final Key valueKey;

  /// Place relative to the current chord (-1 previous, 0 current, 1 next, 2
  /// after that), or null for the song-wide row shown before playing.
  final int? slot;
  final bool isCurrent;
  final bool isPlaceholder;

  /// Part of the song-wide row shown before playing: all cards look alike.
  final bool isStatic;
}

class _ChordCard extends StatelessWidget {
  const _ChordCard({
    required this.entry,
    required this.width,
    required this.chordProgress,
    required this.chordStart,
    required this.chordBeats,
    required this.playbackTime,
  });

  final _StripEntry entry;
  final double width;
  final double? chordProgress;
  final double? chordStart;
  final List<ChordBeat> chordBeats;
  final double playbackTime;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final isCurrent = entry.isCurrent;
    final foreground = isCurrent || entry.isStatic
        ? PracticeStageColors.textPrimary
        : PracticeStageColors.textSecondary;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOutCubic,
      width: entry.isPlaceholder ? width * 0.6 : width,
      padding: const EdgeInsets.fromLTRB(6, 8, 6, 8),
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
          // Size and colour ease between "next" and "now" as the cards move.
          TweenAnimationBuilder<TextStyle>(
            tween: TextStyleTween(
              end: isCurrent
                  ? textTheme.titleLarge!.copyWith(
                      color: PracticeStageColors.amberBright,
                      fontWeight: FontWeight.w800,
                      height: 1.1,
                    )
                  : textTheme.titleMedium!.copyWith(
                      color: entry.isStatic
                          ? PracticeStageColors.textPrimary
                          : PracticeStageColors.textSecondary,
                      fontWeight: FontWeight.w600,
                      height: 1.1,
                    ),
            ),
            duration: const Duration(milliseconds: 320),
            curve: Curves.easeOutCubic,
            builder: (context, style, _) => Text(
              chordDisplayName(entry.chord),
              key: entry.valueKey,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: style,
            ),
          ),
          const SizedBox(height: 6),
          Expanded(
            child: Center(
              child: entry.isPlaceholder
                  ? const SizedBox.shrink()
                  : FittedBox(
                      fit: BoxFit.contain,
                      // The shape's colour eases between "next" and "now".
                      child: TweenAnimationBuilder<Color?>(
                        tween: ColorTween(end: foreground),
                        duration: const Duration(milliseconds: 320),
                        curve: Curves.easeOutCubic,
                        builder: (context, color, _) => ChordDiagram(
                          chord: entry.chord,
                          foregroundColor: color ?? foreground,
                          accentColor: color ?? foreground,
                        ),
                      ),
                    ),
            ),
          ),
          if (isCurrent) ...[
            const SizedBox(height: 6),
            if (chordBeats.isNotEmpty &&
                chordBeats.length <= ChordDiagramStrip.maximumBeatSegments)
              _ChordBeatSegments(
                key: const ValueKey('chordBeatSegments'),
                beats: chordBeats,
                playbackTime: playbackTime,
                chordStart: chordStart,
              )
            else
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

/// One segment per beat of the chord, so a player can count the strums: the
/// beats already played are filled, and the one playing fills as it goes.
class _ChordBeatSegments extends StatelessWidget {
  const _ChordBeatSegments({
    super.key,
    required this.beats,
    required this.playbackTime,
    required this.chordStart,
  });

  final List<ChordBeat> beats;
  final double playbackTime;
  final double? chordStart;

  static const _gap = 3.0;
  static const _height = 6.0;

  @override
  Widget build(BuildContext context) {
    var playing = beats.lastIndexWhere((beat) => beat.start <= playbackTime);
    if (playing < 0) playing = 0;
    return Semantics(
      label: 'Beat ${playing + 1} of ${beats.length}',
      child: SizedBox(
        height: _height,
        child: Row(
          children: [
            for (var index = 0; index < beats.length; index++) ...[
              if (index > 0) const SizedBox(width: _gap),
              Expanded(
                child: _BeatSegment(
                  key: ValueKey('beatSegment$index'),
                  height: _height,
                  fill: beats[index].fillAt(playbackTime),
                  resetKey: chordStart,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _BeatSegment extends StatelessWidget {
  const _BeatSegment({
    super.key,
    required this.height,
    required this.fill,
    required this.resetKey,
  });

  final double height;
  final double fill;
  final double? resetKey;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      key: ValueKey(resetKey),
      tween: Tween(end: fill),
      duration: const Duration(milliseconds: 180),
      curve: Curves.linear,
      builder: (context, value, child) => ClipRRect(
        borderRadius: BorderRadius.circular(height / 2),
        child: SizedBox(
          height: height,
          child: Stack(
            fit: StackFit.expand,
            children: [
              const ColoredBox(color: PracticeStageColors.border),
              Align(
                alignment: Alignment.centerLeft,
                child: FractionallySizedBox(
                  widthFactor: value,
                  heightFactor: 1,
                  child: const ColoredBox(
                    color: PracticeStageColors.amberBright,
                  ),
                ),
              ),
            ],
          ),
        ),
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

/// What the player reads for a chord label: "N" (no chord) is a rest.
String chordDisplayName(String chord) => chord == 'N' ? 'Rest' : chord;
