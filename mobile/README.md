# ChordSync Flutter Client

This directory contains the Flutter client for ChordSync, a final-year Music
Information Retrieval and software engineering project for synchronised guitar
practice.

## Current Functionality

- Loads and deserializes a Python-generated `SharedTimeline` JSON asset.
- Models bars, beat events, chords, lyric segments, and word timings.
- Resolves the current chord, beat/downbeat state, and active lyric word for a
  playback timestamp.
- Provides a small playback-position controller that supports forward and
  backward seeking in tests.

Real audio playback and the complete practice interface are planned for later
tasks.

## Setup

From this directory, resolve Flutter dependencies:

```sh
flutter pub get
```

## Verification

Run the test suite:

```sh
flutter test
```

Run static analysis:

```sh
flutter analyze
```

The practice-timeline tests exercise both controlled timelines and the bundled
`SharedTimeline` asset. The asset is a temporary research fixture and remains
subject to the repository's data-publication review.
