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
- Provides a typed analysis API client for uploading local audio, checking job
  status, and parsing completed results with the existing `SharedTimeline`
  model.
- Converts completed analysis into a practice session that keeps the returned
  timeline paired with an app-owned copy of the selected local audio file. The
  server analyzes an uploaded copy; practice playback uses the persisted local
  copy through the existing controller and synchronization stack.
- Provides the first functional user journey: choose a local WAV, MP3, or M4A
  file, review its safe metadata, analyze it with visible upload/job state, and
  explicitly enter the song-sheet practice screen when ready.

## Visual direction

The client follows an **Acoustic / Warm / Natural** identity: walnut controls,
cream and parchment-like sheet surfaces, and restrained honey accents. Georgia
serif headings and chord display pair with the platform sans-serif for controls;
this avoids an additional font dependency. The user flow is Add → Analyze →
Sheet. Active, success, and error states always have a label, shape, weight, or
icon in addition to color. Home, Tuner, and Settings remain deferred; no
placeholder destinations are exposed.

## Setup

From this directory, resolve Flutter dependencies:

```sh
flutter pub get
```

The development API base URL defaults to `http://127.0.0.1:8000`. Override it
for a simulator or device with a compile-time setting appropriate to the local
network environment:

```sh
flutter run --dart-define=CHORDSYNC_API_BASE_URL=http://127.0.0.1:8000
```

Do not commit machine-specific network addresses. A deployed client should use
an HTTPS API URL.

The analysis client sends `title` and a file-backed `audio` part as multipart
form data and can report upload byte progress. Its polling service checks once
per second by default, stops after 15 minutes, fetches the result only after a
job completes, and supports client-side cancellation. Cancellation stops local
polling; it does not currently cancel work on the backend.

Cancelling from the import screen only stops local waiting. The backend job may
continue independently, while the selected file remains available for an
explicit retry that creates a new job. Returning from practice preserves the
ready result and selection. Broader song-library navigation remains pending.

Selected audio is copied immediately into the app's Documents
`imported_audio/` directory, so practice does not depend on a temporary native
picker path. Successful imports are retained for analysis and practice, including
retries and return navigation. There is no automatic deletion in this phase:
library ownership, duplicate detection, orphan cleanup, and retention limits
are deferred. An import that fails partway removes its partial copy when
possible.

## Verification

Run the test suite:

```sh
flutter test
```

Run static analysis:

```sh
flutter analyze
```

With the local API and analysis environments running, the opt-in native smoke
test exercises the real upload, polling, analyzed-session, local-file playback,
and practice-screen path:

```sh
flutter test integration_test/s5_t06_real_smoke_test.dart -d macos \
  --dart-define=CHORDSYNC_API_BASE_URL=http://127.0.0.1:8765
```

The complete user-facing import journey has a separate native smoke test:

```sh
flutter test integration_test/s5_t07_real_user_flow_test.dart -d macos \
  --dart-define=CHORDSYNC_API_BASE_URL=http://127.0.0.1:8765
```

The practice-timeline tests exercise controlled timelines and the bundled
synthetic `SharedTimeline` and audio fixtures. Both fixtures were created for
ChordSync testing and contain no commercial song audio or lyrics.
