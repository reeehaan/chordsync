import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../design_system/chordsync_design_system.dart';
import 'upload_theme.dart';

/// True on iOS/macOS, so source badges can use the Cupertino icon set and
/// otherwise fall back to Material icons for Android and other platforms.
bool _prefersCupertinoIcons(BuildContext context) {
  final platform = Theme.of(context).platform;
  return platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;
}

/// Grid of places a song can come from on the upload tab.
class SongSourceGrid extends StatelessWidget {
  const SongSourceGrid({
    super.key,
    required this.compact,
    required this.onFiles,
    required this.onYouTube,
    required this.onCameraRoll,
    required this.onRecord,
    required this.onShazam,
  });

  final bool compact;
  final VoidCallback onFiles;
  final VoidCallback onYouTube;
  final VoidCallback onCameraRoll;
  final VoidCallback onRecord;
  final VoidCallback onShazam;

  @override
  Widget build(BuildContext context) {
    final cupertino = _prefersCupertinoIcons(context);
    final sources = [
      _SongSource(
        key: 'youtubeSource',
        title: 'YouTube',
        description: 'Pick any song or video',
        onTap: onYouTube,
        badgeBuilder: (size) => _AssetBadge(
          'assets/icons/source_providers/youtube_icon.png',
          size: size,
        ),
      ),
      _SongSource(
        key: 'cameraRollSource',
        title: 'Camera Roll',
        description: 'Upload a video from your photo library',
        onTap: onCameraRoll,
        badgeBuilder: (size) => _SvgBadge(
          'assets/icons/source_providers/gallery.svg',
          background: UploadPalette.primaryText,
          size: size,
        ),
      ),
      _SongSource(
        key: 'filesSource',
        title: 'Files',
        description: 'Upload from local files',
        onTap: onFiles,
        badgeBuilder: (size) => _SvgBadge(
          'assets/icons/source_providers/folder.svg',
          background: UploadPalette.primaryText,
          size: size,
        ),
      ),
      _SongSource(
        key: 'recordSource',
        title: 'Record',
        description: 'Record your own audio',
        onTap: onRecord,
        badgeBuilder: (size) => _IconBadge(
          icon: cupertino ? CupertinoIcons.mic_fill : Icons.mic_rounded,
          foreground: Colors.white,
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFFFF6A3D), Color(0xFFE53935)],
          ),
          size: size,
        ),
      ),
      _SongSource(
        key: 'shazamSource',
        title: 'Shazam',
        description: 'Identify a song with Shazam',
        onTap: onShazam,
        badgeBuilder: (size) =>
            _SvgBadge('assets/icons/source_providers/shazem.svg', size: size),
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: sources.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: compact ? 0.9 : 1.05,
          ),
          itemBuilder: (context, index) => _SourceCard(source: sources[index]),
        ),
        const SizedBox(height: 12),
        Text(
          'Phone audio: WAV · MP3 · M4A',
          style: Theme.of(
            context,
          ).textTheme.labelMedium?.copyWith(color: UploadPalette.secondaryText),
        ),
      ],
    );
  }
}

class _SongSource {
  const _SongSource({
    required this.key,
    required this.title,
    required this.description,
    required this.onTap,
    required this.badgeBuilder,
  });

  final String key;
  final String title;
  final String description;
  final VoidCallback onTap;

  /// Builds this source's badge at the given square size. Sizing is driven
  /// by the card's own LayoutBuilder (see `_SourceCard`) so the badge still
  /// shrinks to fit a tight/compact card instead of overflowing it.
  final Widget Function(double size) badgeBuilder;
}

const _badgeRadius = 16.0;

/// A source's square app-icon-style mark. Each source owns its own badge so
/// brand marks (an image, or Shazam's circular mark) and generic utility
/// icons (Camera Roll, Files, Record) can each use the right shape.
class _AssetBadge extends StatelessWidget {
  const _AssetBadge(this.assetPath, {required this.size});

  final String assetPath;
  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Image.asset(assetPath, fit: BoxFit.contain),
    );
  }
}

class _IconBadge extends StatelessWidget {
  const _IconBadge({
    required this.icon,
    required this.foreground,
    required this.size,
    this.background,
    this.gradient,
  }) : assert(
         background != null || gradient != null,
         'An icon badge needs either a solid background or a gradient.',
       );

  final IconData icon;
  final Color foreground;
  final double size;
  final Color? background;
  final Gradient? gradient;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: background,
        gradient: gradient,
        borderRadius: BorderRadius.circular(_badgeRadius),
      ),
      child: Icon(icon, color: foreground, size: size * 0.46),
    );
  }
}

/// An SVG source-provider mark. [background] draws a squircle backdrop for
/// glyphs whose own artwork has a transparent background (Camera Roll,
/// Files); leaving it null is for artwork that already fills its own tile
/// edge-to-edge (Shazam's mark already paints a full-bleed background).
class _SvgBadge extends StatelessWidget {
  const _SvgBadge(this.assetPath, {required this.size, this.background});

  final String assetPath;
  final double size;
  final Color? background;

  @override
  Widget build(BuildContext context) {
    if (background == null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(_badgeRadius),
        child: SvgPicture.asset(assetPath, width: size, height: size),
      );
    }
    final padding = size * 0.14;
    final contentSize = size - padding * 2;
    return Container(
      width: size,
      height: size,
      padding: EdgeInsets.all(padding),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(_badgeRadius),
      ),
      child: SvgPicture.asset(
        assetPath,
        width: contentSize,
        height: contentSize,
      ),
    );
  }
}

class _SourceCard extends StatelessWidget {
  const _SourceCard({required this.source});

  final _SongSource source;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: UploadPalette.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ChordSyncRadii.card),
        side: const BorderSide(color: UploadPalette.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: ValueKey(source.key),
        onTap: source.onTap,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final tight = constraints.maxHeight < 180;
            final badgeSize = tight ? 46.0 : 54.0;
            return Padding(
              padding: EdgeInsets.all(tight ? 8 : 16),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  source.badgeBuilder(badgeSize),
                  SizedBox(height: tight ? 6 : 11),
                  Text(
                    source.title,
                    style: tight
                        ? Theme.of(context).textTheme.titleSmall
                        : Theme.of(context).textTheme.titleMedium,
                  ),
                  SizedBox(height: tight ? 2 : 3),
                  Text(
                    source.description,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: UploadPalette.secondaryText,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
