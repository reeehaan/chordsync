# Source provider icons

Place approved provider artwork in this directory using these names:

- `spotify_icon.svg` or `spotify_icon.png`
- `youtube_icon.svg` or `youtube_icon.png`
- `shazam_icon.svg` or `shazam_icon.png`

Download only from each provider's official brand-resource page and retain the
original proportions and colors. Do not place Apple Photos, Apple Files, Home,
Add, Microphone, or Tuner artwork here; ChordSync uses Flutter system icons for
those actions.

SVG files will require adding `flutter_svg` before they can be rendered. PNG
files should preferably have a transparent background and be at least 192×192.

The tuner symbol was created by Gregor Cresnar for the Noun Project. Its visible
canvas is cropped for navigation use; attribution is retained here.
