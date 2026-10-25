# Splash screen guitar samples

- Asset: `mobile/assets/audio/splash_harmonics.wav` (3.6 s, 44.1 kHz mono)
- Made by: `mobile/tool/generate_splash_chord.py`, from five recordings
- Recordings used: acoustic guitar open strings G2, C3, G3, C4 and E4
- Source set: "guitar-acoustic" in
  <https://github.com/nbrosowsky/tonejs-instruments> (`samples/guitar-acoustic/`),
  commit read on 2026-10-25
- Original recordings: University of Iowa Electronic Music Studios, Musical
  Instrument Samples, <http://theremin.music.uiowa.edu/> (named for this set in
  the project's `sample-source-info.txt`)
- License of the packaged samples: Creative Commons Attribution 3.0
  (<https://creativecommons.org/licenses/by/3.0/>), per the project's README
- Status: **APPROVED FOR THE PRIVATE DEMO BUILD — ATTRIBUTION OWED BEFORE ANY
  PUBLIC RELEASE**

## What the app does with them

The app plays one sound once at launch, on the splash screen: a short tab of
natural harmonics (12th and 7th fret) in open C tuning, so C major. The sound
is a derived work, not the original recordings:

- each note is a comb-filtered copy of one open-string recording, so only the
  overtones a harmonic keeps are left;
- the highs are boosted slightly and a short bright tick is added at the start;
- the notes are mixed 160 ms apart, shaped with a fade and normalised.

The recordings themselves are not shipped, only the mixed result. Rebuilding
needs the five .wav files and `python3 tool/generate_splash_chord.py <folder>`.

## Credit to give

> Guitar sounds: University of Iowa Electronic Music Studios (Musical
> Instrument Samples), via the tonejs-instruments sample library by Nick
> Brosowsky, CC BY 3.0. Edited and mixed for ChordSync.

## Open points

- The app has no credits or About screen yet. CC BY asks for credit in a way
  that fits the medium; for the private demo this file is the record. **Add the
  credit above to an in-app credits screen before the app goes to any other
  users or a store.**
- Not used: the "guitar-nylon" set in the same library (from Freesound sound
  11573, whose own license was not checked), and any audio from YouTube
  lessons. Do not add either without reading the license first.
- If the sound is ever replaced by the owner's own recording of harmonics, this
  file and the generator can be removed.
