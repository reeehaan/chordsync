# Analysis worker container

The worker uses one Linux image while preserving the dependency isolation used
by local production analysis:

```text
/opt/chordsync/
  app/                    application source (BAKED_IN_IMAGE)
  venvs/
    backend/              API, queue, storage, and publication dependencies
    btc/                  BTC and its Torch stack
    beats/                Python 3.10, madmom, and its pinned NumPy stack
    whisperx/             WhisperX and its Torch stack
    demucs/               Demucs and its Torch/TorchCodec stack
  models/
    btc/source/           EXTERNAL_MOUNT: upstream BTC checkout
    btc/btc_model.pt      EXTERNAL_MOUNT: separately obtained checkpoint
  cache/
    huggingface/          MODEL_CACHE: WhisperX and alignment models
    torch/                MODEL_CACHE: Demucs weights
```

`/tmp/chordsync` is the writable per-job workspace. The application source is
not a runtime write location, and the container runs as the non-root
`chordsync` user.

## Dependency classification

| Dependency | Strategy | Note |
| --- | --- | --- |
| ffmpeg / ffprobe | BAKED_IN_IMAGE | Installed from the pinned Debian release used by the base image. |
| libsndfile | BAKED_IN_IMAGE | Runtime and build packages are installed. |
| Rubber Band | BAKED_IN_IMAGE | Required by the BTC environment through `pyrubberband`. |
| compiler/build tools | BAKED_IN_IMAGE | Needed to build native Python packages, notably madmom. |
| Chordino/Vamp host and plugin | UNRESOLVED | Debian packaging/provenance and plugin discovery must be proven before enabling the optional diagnostic in this image. |
| application source | BAKED_IN_IMAGE | Copied from the reviewed build context. |
| BTC source | EXTERNAL_MOUNT | Upstream MIT-licensed source is not vendored by ChordSync. |
| BTC checkpoint | EXTERNAL_MOUNT | Upstream does not clearly license pretrained checkpoint redistribution; its SHA-256 must be checked before use. |
| madmom packaged models | BAKED_IN_IMAGE | Supplied by the pinned package in a Python 3.10 multi-stage environment; the remaining environments use Python 3.11. |
| WhisperX model | MODEL_CACHE | Downloaded on first use into the persistent Hugging Face cache. |
| WhisperX alignment model | MODEL_CACHE | Language-dependent first-use download. |
| Demucs `htdemucs` weights | MODEL_CACHE | Downloaded on first use into the persistent Torch cache. |

The image is CPU-safe by design: Python installation also uses PyTorch's
official CPU wheel index, and it does not set a CUDA or Apple MPS device. GPU
readiness is intentionally not claimed by this CPU base image. First use
requires network access or a pre-populated persistent cache for WhisperX,
alignment, and Demucs model assets.

## Build and smoke commands

Run from the repository root:

```sh
docker buildx build --load --platform linux/arm64 \
  --file backend/worker/Dockerfile --tag chordsync-worker:s6-t10-arm64 .

docker run --rm chordsync-worker:s6-t10-arm64 ffmpeg -version
docker run --rm chordsync-worker:s6-t10-arm64 ffprobe -version
docker run --rm chordsync-worker:s6-t10-arm64 \
  python -m backend.api.app.analysis_worker --help
docker run --rm chordsync-worker:s6-t10-arm64 \
  python -m backend.api.app.analysis_worker_consumer --help
```

An amd64 proof uses `--platform linux/amd64` and a distinct local tag. Do not
push either image until the native tools, all isolated imports, BTC mounts, and
model-cache behavior have been verified on Linux.
