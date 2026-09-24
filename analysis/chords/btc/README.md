# BTC neural chord estimator

ChordSync integrates the 25-class major/minor/no-chord mode of
[BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19), the MIT-licensed code
released with Park et al., “A Bi-Directional Transformer for Musical Chord
Recognition,” ISMIR 2019. BTC is the preferred estimator once its local
environment is configured (see below); Chordino remains the fallback
wherever BTC isn't set up.

## Local setup

Use Python 3.11 in an isolated environment. Do not install Torch or the BTC
runtime into the FastAPI environment.

```sh
python3.11 -m venv analysis/chords/btc/.venv-btc
analysis/chords/btc/.venv-btc/bin/python -m pip install \
  -r analysis/chords/btc/requirements.txt
```

Keep an upstream BTC checkout and checkpoint outside Git. The upstream
repository contains an MIT license, but does not state separate terms for its
pretrained checkpoints. ChordSync therefore neither commits nor redistributes
the weights. The verified upstream checkout was commit
`2682317be668032e6e4b269ded36adaa2ad57df0`; verify the local 25-class model
against `checkpoint.sha256` before use.

Configure local paths without committing machine-specific values:

```sh
export CHORDSYNC_BTC_PYTHON=/path/to/.venv-btc/bin/python
export CHORDSYNC_BTC_SOURCE=/path/to/BTC-ISMIR19
export CHORDSYNC_BTC_CHECKPOINT=/path/to/btc_model.pt
```

`AnalysisPipelineConfig.local()` switches to BTC automatically once all three
paths above are set — no separate opt-in variable needed. Set
`CHORDSYNC_CHORD_ESTIMATOR` explicitly (`chordino` or `btc`) to override that
choice either way. With none of the BTC variables set, the default remains
`chordino`. Run BTC independently with explicit paths:

```sh
analysis/chords/btc/.venv-btc/bin/python -m analysis.pipeline_cli btc-chords \
  --input /path/to/normalized.wav \
  --output /path/to/btc-chords.json \
  --source /path/to/BTC-ISMIR19 \
  --checkpoint /path/to/btc_model.pt
```

Inference prefers Apple MPS when PyTorch reports it available, then CUDA, then
CPU. The verified local upstream needed modern PyYAML, NumPy, and PyTorch
checkpoint-loading compatibility changes. The 25-class model ran on MPS on an
8 GB M2; CPU fallback also ran successfully when MPS was unavailable.

## Output contract and vocabulary

Both estimators produce the canonical `ChordSegment` fields: `start`, `end`,
`raw_label`, `normalized_label`, and `source`. BTC's 25 labels are the 12 major
roots, 12 `:min` roots, and `N`. Existing ChordSync normalization maps `C:maj`
to `C`, `A:min` to `Am`, and `N` to `N`; enharmonic flats use the existing
sharp-root convention. No additional smoothing is performed.

The upstream checkpoint uses an eight-layer, four-head bi-directional
Transformer with 144-bin CQT input features, as recorded by its checked-in
`run_config.yaml`.

The deterministic twelve-second fixture in `tests/fixtures/audio/` contains
equal-tempered sine-wave triads C, Am, F, and G, each lasting three seconds. It
has no melody, vocals, or third-party recording, and can be regenerated with
`generate_synthetic_fixture.py`.
