# Chord evaluation artifacts

ChordSync keeps third-party reference data separate from project-generated
prediction output.

## Local reference annotation

`annotations/let_it_be.lab` is a locally supplied third-party reference used by
the original Sprint 1 evaluation. Project documentation identifies it as an
Isophonics chord annotation. Its original URL, release identifier, authorship
details, and redistribution terms are not recorded in the current experiment
metadata. It is therefore intended to remain local unless those terms are
independently verified.

Run the comparison with an explicitly supplied local reference:

```sh
python -m analysis.evaluation.compare_estimators \
  --reference path/to/local-reference.lab
```

No reference annotation is downloaded automatically.

## Retained predictions

Both retained `.lab` files use one row per estimated segment:

```text
start_time end_time chord_label
```

They contain timestamps and symbolic chord labels only. They do not contain
source audio or lyrics. The evaluation audio was supplied locally and is not
distributed by the intended public repository.

### BTC

- File: `predictions/btc/let_it_be.lab`
- Estimator: BTC
- Origin: generated locally for the ChordSync Sprint 1 evaluation workflow
- Project integration: `analysis/chords/btc/btc_parser.py`
- Exact external implementation commit: not recorded in the current experiment
  metadata
- Exact model checkpoint and configuration: not recorded in the current
  experiment metadata
- Exact generation command: not recorded in the current experiment metadata

### Chordino

- File: `predictions/chordino/let_it_be.lab`
- Estimator: Chordino through Sonic Annotator/NNLS-Chroma
- Origin: generated locally for the ChordSync Sprint 1 evaluation workflow
- Project integration: `analysis/chords/chordino/chordino_runner.py`
- Exact Sonic Annotator and plugin versions: not recorded in the current
  experiment metadata
- Exact normalized `.lab` export command: not recorded in the current experiment
  metadata

The predictions can be parsed and evaluated by the repository, but reproducing
the exact historical outputs requires the missing estimator metadata and
locally supplied evaluation audio.
