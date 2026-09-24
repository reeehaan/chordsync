# Demucs vocal separation

ChordSync runs [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs`)
as a pipeline stage between beat/chord analysis and lyric transcription.
Chords and beats still run against the full mix — separation would strip the
harmonic and rhythmic content those estimators need. Only the WhisperX lyric
stage consumes the isolated vocal stem, since removing instrumental bleed is
what actually improves transcription accuracy on sung audio.

## Local setup

Use an isolated environment; Demucs pulls in Torch and should not be
installed into the FastAPI environment.

```sh
python3.11 -m venv analysis/separation/.venv-separation
analysis/separation/.venv-separation/bin/python -m pip install \
  -r analysis/separation/requirements.txt
```

`RealAnalysisProcessor.process()` invokes the venv's `demucs` console script
directly (the same pattern used for the WhisperX CLI) — no wrapper module is
needed because Demucs already produces its stem output as a plain WAV file:

```sh
analysis/separation/.venv-separation/bin/demucs \
  -n htdemucs --two-stems vocals -d cpu \
  -o /path/to/workspace/separated \
  /path/to/workspace/normalized.wav
```

This writes the isolated vocal stem to
`separated/htdemucs/normalized/vocals.wav`, which is what gets handed to
WhisperX.

## Configuration

No environment variable is required — `AnalysisPipelineConfig.local()`
defaults `demucs_executable` to `analysis/separation/.venv-separation/bin/demucs`
and `demucs_model` to `htdemucs`. Override the executable path directly on
`AnalysisPipelineConfig` if you keep the venv elsewhere.
