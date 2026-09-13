# ChordSync Flutter Client

This directory contains the Flutter client for ChordSync, a final-year Music
Information Retrieval and software engineering project for synchronised guitar
practice.

## Current Functionality

- Loads and deserializes a Python-generated `SharedTimeline` JSON asset.
- Models bars, beat events, chords, lyric segments, and word timings.
- Resolves the current chord, beat/downbeat state, and active lyric word for a
  playback timestamp.
- Plays a bundled publication-safe synthetic audio fixture through
  `just_audio` while keeping media position authoritative.
- Provides seeking, completion/replay handling, playback-speed selection,
  A/B looping, previous/next bar navigation, and synchronized chord, lyric,
  rhythm, and progression context.
- Presents the practice state in a responsive, scrollable interface for phone
  and desktop-sized layouts.

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

The practice-timeline tests exercise controlled timelines and the bundled
synthetic `SharedTimeline` and audio fixtures. Both fixtures were created for
ChordSync testing and contain no commercial song audio or lyrics.
