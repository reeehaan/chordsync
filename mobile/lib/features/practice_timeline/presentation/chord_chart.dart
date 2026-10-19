import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../data/shared_timeline.dart';

/// The song's chords bar by bar, shown when there are no lyrics to put them
/// over. The bar being played is highlighted and the chart follows along.
class ChordChart extends StatefulWidget {
  const ChordChart({
    super.key,
    required this.timeline,
    required this.playbackTime,
  });

  final SharedTimeline timeline;
  final double playbackTime;

  static const barsPerRow = 4;
  static const rowExtent = 76.0;

  /// The chords played inside one bar, in order, without "no chord" gaps.
  static List<String> chordsOf(TimelineBar bar) {
    final chords = <String>[];
    for (final beat in bar.beats) {
      if (beat.chord == 'N') continue;
      if (chords.isEmpty || chords.last != beat.chord) chords.add(beat.chord);
    }
    return chords;
  }

  /// Index of the bar sounding at [time], or the last one that has started.
  static int currentBar(List<TimelineBar> bars, double time) {
    var current = 0;
    for (var index = 0; index < bars.length; index++) {
      if (bars[index].startTime <= time) current = index;
    }
    return current;
  }

  @override
  State<ChordChart> createState() => _ChordChartState();
}

class _ChordChartState extends State<ChordChart> {
  final ScrollController _controller = ScrollController();
  bool _autoFollow = true;
  int _row = 0;

  List<TimelineBar> get _bars => widget.timeline.bars;

  @override
  void initState() {
    super.initState();
    _row = _currentRow();
    _scheduleFollow(jump: true);
  }

  @override
  void didUpdateWidget(covariant ChordChart oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = _row;
    _row = _currentRow();
    if (_row != previous && _autoFollow) _scheduleFollow();
  }

  int _currentRow() =>
      ChordChart.currentBar(_bars, widget.playbackTime) ~/
      ChordChart.barsPerRow;

  void _scheduleFollow({bool jump = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_autoFollow || !_controller.hasClients) return;
      final position = _controller.position;
      final target =
          (_row * ChordChart.rowExtent -
                  (position.viewportDimension - ChordChart.rowExtent) / 2)
              .clamp(0.0, position.maxScrollExtent);
      if (jump) {
        _controller.jumpTo(target);
      } else {
        _controller.animateTo(
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

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final rows = (_bars.length / ChordChart.barsPerRow).ceil();
    final current = ChordChart.currentBar(_bars, widget.playbackTime);
    return Stack(
      children: [
        NotificationListener<UserScrollNotification>(
          onNotification: _handleUserScroll,
          child: ListView.builder(
            key: const ValueKey('chordChart'),
            controller: _controller,
            physics: const AlwaysScrollableScrollPhysics(
              parent: ClampingScrollPhysics(),
            ),
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            itemExtent: ChordChart.rowExtent,
            itemCount: rows,
            itemBuilder: (context, row) => Row(
              children: [
                for (var column = 0; column < ChordChart.barsPerRow; column++)
                  Expanded(
                    child: _bar(row * ChordChart.barsPerRow + column, current),
                  ),
              ],
            ),
          ),
        ),
        if (!_autoFollow)
          Positioned(
            right: 12,
            bottom: 12,
            child: FilledButton.tonalIcon(
              key: const ValueKey('followChordsButton'),
              onPressed: () {
                setState(() => _autoFollow = true);
                _scheduleFollow();
              },
              icon: const Icon(Icons.my_location, size: 17),
              label: const Text('Follow'),
            ),
          ),
      ],
    );
  }

  Widget _bar(int index, int current) {
    if (index >= _bars.length) return const SizedBox.shrink();
    return _BarCell(
      key: ValueKey('chartBar$index'),
      number: _bars[index].barNumber,
      chords: ChordChart.chordsOf(_bars[index]),
      state: index == current
          ? _BarState.playing
          : index < current
          ? _BarState.played
          : _BarState.upcoming,
    );
  }
}

enum _BarState { upcoming, played, playing }

class _BarCell extends StatelessWidget {
  const _BarCell({
    super.key,
    required this.number,
    required this.chords,
    required this.state,
  });

  final int number;
  final List<String> chords;
  final _BarState state;

  @override
  Widget build(BuildContext context) {
    final playing = state == _BarState.playing;
    final textColor = switch (state) {
      _BarState.upcoming => ChordSyncColors.chipTextUpcoming,
      _BarState.played => ChordSyncColors.chipTextPlayed,
      _BarState.playing => ChordSyncColors.surface,
    };
    final theme = Theme.of(context).textTheme;
    return Container(
      margin: const EdgeInsets.all(4),
      padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
      decoration: BoxDecoration(
        color: playing
            ? ChordSyncColors.currentChord
            : ChordSyncColors.inactiveChord,
        border: Border.all(
          color: state == _BarState.played
              ? ChordSyncColors.chipBorderPlayed
              : ChordSyncColors.chipBorderUpcoming,
          width: 1.2,
        ),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$number',
            style: theme.labelSmall?.copyWith(
              color: textColor.withValues(alpha: 0.7),
            ),
          ),
          const Spacer(),
          Align(
            alignment: Alignment.center,
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                chords.isEmpty ? '–' : chords.join('  '),
                maxLines: 1,
                style: theme.titleMedium?.copyWith(
                  color: textColor,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }
}
