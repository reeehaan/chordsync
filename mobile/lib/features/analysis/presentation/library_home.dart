import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../practice_timeline/data/song_identity.dart';
import '../application/analyzed_practice_session.dart';
import '../data/embedded_cover_art.dart';
import 'upload_theme.dart';

/// The "Your songs" tab listing previously analyzed practice sessions.
class LibraryHome extends StatefulWidget {
  const LibraryHome({
    super.key,
    required this.sessions,
    required this.onOpen,
    required this.onAddSong,
  });

  final List<AnalyzedPracticeSession> sessions;
  final ValueChanged<AnalyzedPracticeSession> onOpen;
  final VoidCallback onAddSong;

  @override
  State<LibraryHome> createState() => _LibraryHomeState();
}

class _LibraryHomeState extends State<LibraryHome> {
  final TextEditingController _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Songs whose title or artist contains every word typed, in any order.
  List<AnalyzedPracticeSession> get _matches {
    final words = _query
        .toLowerCase()
        .split(RegExp(r'\s+'))
        .where((word) => word.isNotEmpty)
        .toList();
    if (words.isEmpty) return widget.sessions;
    return [
      for (final session in widget.sessions)
        if (_containsAll(_haystack(session), words)) session,
    ];
  }

  static bool _containsAll(String text, List<String> words) =>
      words.every(text.contains);

  static String _haystack(AnalyzedPracticeSession session) {
    final identity = SongIdentity.fromFileName(session.title);
    return '${identity.title} ${identity.artist ?? ''} ${session.title}'
        .toLowerCase();
  }

  @override
  Widget build(BuildContext context) {
    final sessions = widget.sessions;
    final matches = _matches;
    final searching = _query.trim().isNotEmpty;
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 28, 20, 32),
      children: [
        Text('Your songs', style: Theme.of(context).textTheme.displayMedium),
        const SizedBox(height: 8),
        Text(
          'Pick up where you left off.',
          style: Theme.of(
            context,
          ).textTheme.bodyLarge?.copyWith(color: UploadPalette.secondaryText),
        ),
        const SizedBox(height: 20),
        if (sessions.isNotEmpty) ...[
          TextField(
            key: const ValueKey('songSearchField'),
            controller: _search,
            onChanged: (value) => setState(() => _query = value),
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Search songs or artists',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: searching
                  ? IconButton(
                      key: const ValueKey('clearSongSearch'),
                      tooltip: 'Clear search',
                      icon: const Icon(Icons.close),
                      onPressed: () {
                        _search.clear();
                        setState(() => _query = '');
                      },
                    )
                  : null,
            ),
          ),
          const SizedBox(height: 20),
        ] else
          const SizedBox(height: 8),
        if (sessions.isEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  const Icon(Icons.library_music_outlined, size: 42),
                  const SizedBox(height: 12),
                  Text(
                    'No analyzed songs yet',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Add an audio file to create your first practice sheet.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 18),
                  FilledButton.icon(
                    onPressed: widget.onAddSong,
                    icon: const Icon(Icons.add),
                    label: const Text('Add a song'),
                  ),
                ],
              ),
            ),
          )
        else ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  'Previously analyzed',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Text(
                searching
                    ? '${matches.length} of ${sessions.length}'
                    : '${sessions.length} saved',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: UploadPalette.secondaryText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (matches.isEmpty)
            Padding(
              key: const ValueKey('noSongMatches'),
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Text(
                'No songs match "${_query.trim()}".',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: UploadPalette.secondaryText,
                ),
              ),
            ),
          for (final session in matches)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _SavedPracticeCard(
                key: ValueKey('card-${session.job.jobId}'),
                session: session,
                onOpen: () => widget.onOpen(session),
              ),
            ),
        ],
      ],
    );
  }
}

class _SavedPracticeCard extends StatefulWidget {
  const _SavedPracticeCard({
    super.key,
    required this.session,
    required this.onOpen,
  });

  final AnalyzedPracticeSession session;
  final VoidCallback onOpen;

  @override
  State<_SavedPracticeCard> createState() => _SavedPracticeCardState();
}

class _SavedPracticeCardState extends State<_SavedPracticeCard> {
  /// Covers already read this run, so scrolling back does not read the file
  /// again.
  static final Map<String, Future<Uint8List?>> _covers = {};

  late final Future<Uint8List?> _cover = _covers.putIfAbsent(
    widget.session.audioFile.path,
    () => EmbeddedCoverArt.read(widget.session.audioFile),
  );

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final identity = SongIdentity.fromFileName(session.title);
    final textTheme = Theme.of(context).textTheme;
    final chords = _firstChords(session, 4);
    return Card(
      child: InkWell(
        key: ValueKey('savedPractice-${session.job.jobId}'),
        borderRadius: BorderRadius.circular(16),
        onTap: widget.onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          child: Row(
            children: [
              _CoverTile(future: _cover, seed: identity.title),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      identity.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.titleMedium,
                    ),
                    if (identity.artist != null)
                      Text(
                        identity.artist!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.bodyMedium?.copyWith(
                          color: UploadPalette.secondaryText,
                        ),
                      ),
                    const SizedBox(height: 4),
                    Text(
                      '${_duration(session.timeline.endTime)} · '
                      '${session.timeline.bpm.toStringAsFixed(0)} BPM',
                      style: textTheme.bodySmall?.copyWith(
                        color: UploadPalette.secondaryText,
                      ),
                    ),
                    if (chords.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          for (final chord in chords) _ChordChip(chord),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }

  /// The first [limit] different chords in the order they are played.
  static List<String> _firstChords(AnalyzedPracticeSession session, int limit) {
    final seen = <String>[];
    for (final bar in session.timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.chord != 'N' && !seen.contains(beat.chord)) {
          seen.add(beat.chord);
          if (seen.length == limit) return seen;
        }
      }
    }
    return seen;
  }

  static String _duration(double seconds) {
    final total = seconds.round();
    final secs = (total % 60).toString().padLeft(2, '0');
    return '${total ~/ 60}:$secs';
  }
}

class _ChordChip extends StatelessWidget {
  const _ChordChip(this.chord);

  final String chord;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: UploadPalette.background,
        border: Border.all(color: UploadPalette.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        child: Text(
          chord,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: UploadPalette.primaryText,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

/// The song's embedded cover art, or a coloured tile with its first letter
/// when it has none.
class _CoverTile extends StatelessWidget {
  const _CoverTile({required this.future, required this.seed});

  final Future<Uint8List?> future;
  final String seed;

  static const size = 64.0;

  // Warm tones from the Golden Hour theme, so a missing cover still fits.
  static const _tones = [
    Color(0xFFA8502A),
    Color(0xFFD98A33),
    Color(0xFF6E5A4B),
    Color(0xFF8C6A3F),
    Color(0xFFB4663A),
  ];

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: size,
        height: size,
        child: FutureBuilder<Uint8List?>(
          future: future,
          builder: (context, snapshot) {
            final bytes = snapshot.data;
            if (bytes == null) return _fallback(context);
            return Image.memory(
              bytes,
              key: const ValueKey('coverArt'),
              fit: BoxFit.cover,
              cacheWidth: (size * 3).round(),
              gaplessPlayback: true,
              errorBuilder: (context, error, stack) => _fallback(context),
            );
          },
        ),
      ),
    );
  }

  Widget _fallback(BuildContext context) {
    final letter = seed.trim().isEmpty
        ? '♪'
        : String.fromCharCode(seed.trim().runes.first).toUpperCase();
    final tone =
        _tones[seed.codeUnits.fold(0, (a, b) => a + b) % _tones.length];
    return ColoredBox(
      key: const ValueKey('coverFallback'),
      color: tone,
      child: Center(
        child: Text(
          letter,
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            color: Colors.white,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}
