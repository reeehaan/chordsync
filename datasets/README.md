# ChordSync datasets

This directory contains evaluation annotations, model predictions, and small
fixtures used by the ChordSync research pipeline. Commercial audio is not
intended for distribution through the public repository.

Researchers and users must supply local evaluation audio themselves and keep
restricted recordings outside Git. Public-domain, synthetic, or explicitly
licensed fixtures are preferred when a reproducible automated test needs audio.

For every dataset, annotation, or prediction added here, record where it came
from, how it was produced, and any applicable licence or usage conditions.
Generated predictions should identify the source audio or dataset and the model
configuration where practical.

Reference lyrics and word-level timing data can also require a separate
publication decision. Do not assume that derived annotations are automatically
safe to redistribute. This documentation is a project safeguard, not legal
advice.

Local-only evaluation material belongs in ignored paths such as:

- `datasets/chord_eval/audio/`
- `datasets/lyrics_eval/clips/`
- Apple Numbers working documents (`*.numbers`)

Small annotations or fixtures should only be committed after their provenance
and publication status have been reviewed.

One-off validation scripts that directly depend on local research artifacts may
also be kept outside the public repository. Reusable public tools should accept
their input paths explicitly instead of assuming a particular local dataset.

## Chord evaluation

Third-party reference annotations are supplied locally for evaluation. The
current local reference path is excluded from the intended public repository
unless its redistribution terms are independently verified. The estimator
comparison accepts an explicit local reference through `--reference`; it does
not download or bundle reference annotations.

Normalized BTC and Chordino predictions under `datasets/chord_eval/predictions/`
are ChordSync-generated research outputs. They contain timestamps and symbolic
chord labels only, not source audio or lyrics. The commercial evaluation audio
used to produce them is also supplied locally and is not distributed.

See `datasets/chord_eval/README.md` for the recorded provenance and current
reproduction limitations of the retained prediction files.

The public manifest example at
`analysis/evaluation/evaluation_manifest.example.json` documents the required
provenance fields. Restricted track paths belong in the ignored
`analysis/evaluation/evaluation_manifest.local.json`, never in committed
results; machine-readable evaluation output uses a safe track ID instead.

## Local lyric benchmarks

Manually annotated lyric timing and reference files may contain text derived
from copyrighted works. ChordSync uses these files locally for research and
evaluation, and intentionally excludes them from the intended public
repository.

Reproducible public examples should use synthetic, public-domain, or
appropriately licensed fixtures. Aggregate benchmark results may still be
reported in academic documentation without distributing the underlying local
reference material, subject to the researcher's publication review.
