# S6-T14C offline lyrics stage

The first full cloud run (job `1633d423-…`, 2026-10-12) failed in the WhisperX
lyrics stage. Alignment needs NLTK `punkt_tab`, which was not in the image, so
WhisperX called `nltk.download`. That fetched NLTK's public `index.xml` before
failing to write to `/opt/chordsync/nltk_data`. The S6-T13 asset inventory
missed this dependency.

## Changes

- **Packaged punkt_tab.** The worker Dockerfile adds
  `nltk_data@550b6625…/packages/tokenizers/punkt_tab.zip` with
  `ADD --checksum=sha256:e57f6418…0106` and unpacks it root-owned and
  read-only at `/opt/chordsync/share/nltk_data`. `NLTK_DATA` points there.
  Licensing: `docs/licensing/nltk-punkt-tab.md`.
- **Stage network guard.** With `CHORDSYNC_STAGE_NETWORK=disabled`, every
  analysis subprocess runs with `HTTP(S)_PROXY`/`ALL_PROXY` set to
  `http://127.0.0.1:9` (closed), `NO_PROXY` removed, and `HF_HUB_OFFLINE=1` /
  `TRANSFORMERS_OFFLINE=1` forced. Proxy-aware download fallbacks (NLTK, torch
  hub, Hugging Face) therefore fail at once. NLTK refuses the proxied fetch
  before connecting. The worker's own boto3 calls are unaffected, and local
  development is unchanged unless the variable is set.
- **`MPLCONFIGDIR=/tmp/matplotlib`**, writable by the non-root user. This
  removes the Matplotlib cache warning.
- The new variables are declared after the dependency layers, so the first 20
  image layers (all apt and Python packages) are byte-identical to runtime1.

## torchcodec warning: currently non-blocking, not fixed

pyannote warns that `torchcodec` cannot load (`undefined symbol:
torch_get_mutable_data_ptr`, a torchcodec/torch build mismatch in the WhisperX
environment). The mismatch is still present; it does not affect the current
pipeline. pyannote only needs torchcodec to decode audio files itself.
WhisperX decodes with the `ffmpeg` CLI (`whisperx.audio.load_audio`) and passes
pyannote an in-memory `{"waveform", "sample_rate"}` mapping
(`whisperx/asr.py`), so that code path is never used. The offline smoke test
completed transcription and alignment with the warning present. Revisit if
WhisperX or pyannote is upgraded or starts passing file paths to pyannote.

## Verification

`scripts/worker_offline_lyrics_smoke.sh <image>`:

1. With `--network none`, WhisperX transcribes and aligns synthetic macOS
   text-to-speech using the production arguments and the processor's offline
   environment. Image `worker-d9ef4a3-runtime2`: language `en`, 3 segments,
   27/27 words with start and end times.
2. With the network available and `punkt_tab` hidden, the stage fails with
   `Resource 'punkt_tab' not found`, and NLTK's downloader in the same
   environment reports `Security Violation [pathsec.urlopen]: refusing a
   proxied fetch` instead of downloading.

Unit tests: `tests/test_stage_network_guard.py`.

## Release

- Image `worker-d9ef4a3-runtime2`,
  `sha256:0330563b60f5113395906467c0d1b7dfad6a654675e22f4c56ff928bd53c99aa`.
  The ECR scan on 2026-10-13 found 1 CRITICAL (approved TIFF exception).
  Exceptions were re-bound in `docs/security/container-exceptions.md`.
- Task definition `chordsync-student-demo-worker:3`, which adds `NLTK_DATA`,
  `MPLCONFIGDIR`, and `CHORDSYNC_STAGE_NETWORK=disabled`. Revision 2 is
  deregistered.
