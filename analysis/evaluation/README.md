# Chord estimator evaluation

ChordSync evaluates Chordino and BTC predictions against the same trusted
time-aligned `.lab` reference. Each non-empty row is strictly parsed as:

```text
start_time end_time chord_label
```

Intervals must be finite, non-negative, ordered, and non-overlapping. Labels
from references and both estimators pass through the same project major/minor/
no-chord normalization before evaluation.

## Metrics and alignment

The harness uses `mir_eval.util.adjust_intervals` to clip predictions to the
reference evaluation span and fill uncovered time with `N`. It then uses
`merge_labeled_intervals` to split both streams at every boundary. Scores are
weighted by the resulting interval durations rather than segment index.

Reported metrics are root WCSR, major/minor WCSR, triad WCSR, and duration-based
no-chord precision/recall. Extended-chord metrics are intentionally omitted
because the current BTC checkpoint has only major, minor, and no-chord labels.
Each estimator runtime covers one complete cold estimator call; shared
preprocessing time is recorded separately.

## Running one comparison

Use the isolated evaluation interpreter and provide the local BTC configuration:

```sh
analysis/evaluation/.venv-eval/bin/python \
  -m analysis.evaluation.evaluate_estimators \
  --track-id synthetic-c-am-f-g \
  --audio tests/fixtures/audio/synthetic_c_am_f_g.wav \
  --reference tests/fixtures/audio/synthetic_c_am_f_g.lab \
  --output /tmp/synthetic-comparison.json \
  --btc-python /path/to/.venv-btc/bin/python \
  --btc-source /path/to/BTC-ISMIR19 \
  --btc-checkpoint /path/to/btc_model.pt \
  --btc-version upstream-commit-or-release
```

The JSON stores a safe track ID, metrics, runtimes, estimator identifiers, and
checkpoint checksum—not input paths. The console prints a concise table.

## Dataset and provenance controls

`evaluation_manifest.example.json` demonstrates the safe manifest format.
Create `evaluation_manifest.local.json` for restricted local tracks; it is
ignored by Git. For every real track, record audio source, annotation source,
permitted local research use, and redistribution status. Do not use random
chord websites or AI-generated chords as ground truth, and do not commit audio
or annotations when redistribution permission is unclear.

Formal comparison is ready only after the harness and normalization are frozen,
estimator versions/checksums are recorded, and several authorized real tracks
with trusted references and complete provenance are available. Synthetic scores
validate the workflow only and are not evidence of real-song accuracy.
