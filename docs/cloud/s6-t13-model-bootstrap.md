# S6-T13 model bootstrap, network guardrails, and visibility heartbeat

This ticket adds the code, image, and Terraform the first controlled Fargate
RunTask needs. It does not run a task, apply Terraform, or upload model assets.

## Model files the runtime loads

Paths come from the image's environment (`HF_HOME`, `TORCH_HOME`, BTC
variables). The file names were read from the installed packages, not assumed.

Asset | Loaded by | Path in the image
--- | --- | ---
BTC source | `btc-chords` stage | `$CHORDSYNC_BTC_SOURCE/` (`/opt/chordsync/models/btc/source`)
BTC checkpoint | `btc-chords` stage | `$CHORDSYNC_BTC_CHECKPOINT` (`/opt/chordsync/models/btc/btc_model.pt`)
WhisperX ASR | faster-whisper 1.2.1, `small` → `Systran/faster-whisper-small` | `$HF_HOME/hub/models--Systran--faster-whisper-small/{refs/main, snapshots/<rev>/...}`
WhisperX VAD | whisperx 3.8.6 default `pyannote` VAD | bundled in the package: `whisperx/assets/pytorch_model.bin` (in the image; not staged)
English alignment | torchaudio `WAV2VEC2_ASR_BASE_960H` (WhisperX default for `en`) | `$TORCH_HOME/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth`
Demucs | demucs 4.0.1 `htdemucs` (signature `955717e8`) | `$TORCH_HOME/hub/checkpoints/955717e8-8726e21a.th`
madmom | beats stage | bundled in the madmom 0.16.1 package (in the image; not staged)

faster-whisper loads `config.json`, `preprocessor_config.json` (optional; not
in this revision), `model.bin`, `tokenizer.json`, and `vocabulary.*`. With
`HF_HUB_OFFLINE=1` it resolves `refs/main` to the snapshot directory and never
contacts Hugging Face. torch hub loads checkpoints from `TORCH_HOME` when the
file exists; Demucs additionally checks that the file's SHA-256 starts with
`8726e21a`.

`HF_HUB_OFFLINE=1` stays appropriate: every Hugging Face asset is staged.
Non-English alignment models are not staged; with multilingual lyrics enabled,
languages without a default alignment model already fall back to `--no_align`.
Languages whose default model is a Hugging Face model fail the lyrics stage
until that model is staged.

## Manifest (schema version 1)

`models/releases/<release_id>/manifest.json`:

```json
{
  "schema_version": 1,
  "release_id": "2026.10.1",
  "assets": [
    {
      "asset_name": "demucs-htdemucs",
      "role": "demucs_htdemucs",
      "required": true,
      "source_project": "https://github.com/facebookresearch/demucs",
      "source_revision": "demucs 4.0.1, htdemucs 955717e8",
      "license_status": "permissive",
      "files": [
        {
          "artifact_key": "models/demucs/htdemucs/8726e21a.../955717e8-8726e21a.th",
          "destination": "955717e8-8726e21a.th",
          "sha256": "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4",
          "size_bytes": 84141911
        }
      ]
    }
  ]
}
```

Rules, all enforced by `backend/api/app/services/model_bootstrap.py`:

- Exact field sets; unknown or missing fields are rejected.
- `role` is one of `btc_source`, `btc_checkpoint`, `whisperx_asr`,
  `alignment_en`, `demucs_htdemucs`. All five are required, each at most once,
  and none may be marked `required: false`.
- `destination` is relative to the role's approved root, which comes from the
  task environment, never from the manifest. It is rejected if absolute, empty,
  or containing `.`, `..`, `\`, NUL, or `//`, or if it resolves outside the
  root. Fixed-name roles (`btc_checkpoint`, `alignment_en`, `demucs_htdemucs`)
  accept only the exact file name the runtime loads.
- `artifact_key` must be under `models/` and outside `models/releases/`.
- `sha256` is 64 lowercase hex characters; `size_bytes` is a non-negative
  integer.
- `license_status` is `permissive`, `approved`, or `unresolved`. Assets with
  `unresolved` licensing are never installed.
- `release_id` must equal `CHORDSYNC_MODEL_RELEASE`, and the manifest key must
  be exactly `models/releases/<release>/manifest.json`.

## Bootstrap behaviour

`python -m backend.api.app.analysis_worker_consumer --once` (the image CMD):

1. In AWS mode, read the manifest with `s3:GetObject` (boto3, task role).
2. Validate it completely before downloading anything.
3. For each file, skip it if the destination already matches size and SHA-256.
   Otherwise stream it to a temporary file beside the destination, hashing as
   it writes, abort if it grows past `size_bytes`, check the final size and
   SHA-256, then `os.replace` it into place. The temporary file is always
   removed.
4. Only after every file verifies, build the consumer and poll SQS once.

Any failure (missing manifest or object, malformed manifest, unsafe path,
incomplete role set, size or hash mismatch, unresolved licence, missing
configuration, or an unexpected error) logs `model bootstrap failed ...; queue
not polled` and exits with code 3. The consumer is never constructed, so no
message is received and no job is claimed. Files already verified in that run
may remain; nothing unverified is ever left at a destination. Local runtime
mode skips the bootstrap.

## S3 model layout

```text
models/releases/<release_id>/manifest.json
models/btc/source/<upstream-commit>/...
models/btc/checkpoints/<sha256>/btc_model.pt
models/whisperx/asr/faster-whisper-small/<hf-revision>/refs/main
models/whisperx/asr/faster-whisper-small/<hf-revision>/snapshots/<hf-revision>/...
models/alignment/en/wav2vec2_asr_base_960h/<sha256>/wav2vec2_fairseq_base_ls960_asr_ls960.pth
models/demucs/htdemucs/<sha256>/955717e8-8726e21a.th
```

Content-addressed paths are never overwritten. A new release writes a new
manifest. Nothing is under `models/` yet.

## Provenance (no asset uploaded in this ticket)

Hashes are of the files currently on the development Mac; staging must
re-verify them against upstream.

Asset | Upstream | Revision | SHA-256 | Size | Licence / redistribution
--- | --- | --- | --- | --- | ---
BTC source | github.com/jayg996/BTC-ISMIR19 | `2682317be668032e6e4b269ded36adaa2ad57df0` | per-file at staging | small | MIT (LICENSE in checkout). Redistribution allowed with notice.
BTC checkpoint | same repository, `test/btc_model.pt` | same commit | `71c2c5db17e8c43b8a9a9da5db36ef2d667158c07a214eba16344c154c00bf54` | 12,154,754 | **UNRESOLVED.** No separate terms for the weights; the project README declines to redistribute them.
WhisperX ASR | huggingface.co/Systran/faster-whisper-small | `536b0662742c02347bc0e980a01041f333bce120` | `model.bin` `3e305921…d671` | 483,546,902 (model.bin) | Believed MIT (model card). Verify before staging.
WhisperX VAD | bundled in whisperx 3.8.6 | package | in image | — | Ships in the image; not staged.
English alignment | download.pytorch.org/torchaudio/models | torchaudio 2.8.0 bundle | `488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d` | 377,664,473 | fairseq wav2vec 2.0 weights. Believed MIT. Verify before staging.
Demucs htdemucs | dl.fbaipublicfiles.com/demucs/hybrid_transformer | demucs 4.0.1, `955717e8` | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` | 84,141,911 | MIT (demucs). Verify the weights' terms before staging.

Remaining faster-whisper files: `config.json` `b55496ac…b828` (2,370 bytes),
`tokenizer.json` `fb7b6319…d0ab` (2,203,239), `vocabulary.txt` `34ce3fe1…3913`
(459,861), and `refs/main` `8d5d066a…44c9` (40). The full staged set is about
0.96 GB, which fits the 20 GiB ephemeral storage beside the 5.1 GB image.

**BTC blocker:** the upstream MIT license covers the BTC source code. Its text
does not mention the pretrained checkpoint, and no other evidence states terms
for it, so the checkpoint's licensing and redistribution status is
**unresolved**. It is not covered by MIT for this project's purposes, and no
public or commercial redistribution is permitted. Upload to private S3 remains
blocked pending a separate licensing decision. The bootstrap refuses assets
marked `unresolved`, so the worker cannot run BTC until that decision is
recorded or another chord estimator is chosen.

## Worker IAM

One statement was added to the worker task role: `s3:GetObject` on
`<artifact-bucket>/models/*`. No `ListBucket`, write, or delete permission is
needed, because the bootstrap reads only exact keys named by the manifest.
Existing job-artifact and queue permissions are unchanged.

## Networking for RunTask

- Subnets: the three default-for-AZ subnets of the default VPC
  (`subnet-0b136ed1e5995f9b9`, `subnet-0b86c38e1e72e1d10`,
  `subnet-070706e42ddcc213b`). Verified on 2026-10-11: they have no explicit
  route-table association, and the main route table `rtb-04330def871c8a911`
  routes `0.0.0.0/0` to the attached `igw-0105ae6e2c5cf13fc`. Terraform exposes
  them as `worker_task_subnet_ids`.
- `assignPublicIp = ENABLED`, which Fargate needs to reach ECR, S3, SQS,
  DynamoDB, and CloudWatch Logs without NAT.
- Security group `chordsync-analysis-worker` (`worker_security_group_id`):
  `ingress = []` (enforced), egress TCP 443 to `0.0.0.0/0` only. DNS uses the
  VPC resolver, which security groups do not filter.
- No NAT gateway, no VPC endpoints, no load balancer.

## SQS visibility

Before this ticket, the queue default was 1200 s, but the adapter overrode it
with 900 s on every receive, and nothing extended it during analysis.

Now (`VisibilityPolicy` in `visibility_heartbeat.py`):

- Initial visibility: 1800 s, set on every receive. The adapter default now
  comes from the policy. The queue's own 1200 s default applies only to
  receives that omit a value, and this worker never omits it.
- Heartbeat: while the claimed job is PROCESSING (materialize, analyze,
  publish), a background thread calls `ChangeMessageVisibility` every 300 s
  with 1800 s. At least 1500 s of visibility always remains.
- Cap: heartbeats stop after 3600 s. The stage timeouts total 3240 s, so a
  healthy run finishes first; a hung worker cannot hide a message forever.
- Ordering: the heartbeat is stopped and its thread joined before any
  acknowledge (delete) or release, so an extension can never race a delete.
  Messages are deleted only on the existing completed, stale, and permanent
  failure paths.
- Extension failures are logged with the job ID and error type only (never the
  receipt handle). The worker keeps going; at worst the message reappears, and
  the conditional QUEUED→PROCESSING claim and RELEASED_BUSY path reject the
  duplicate.
- Retry and DLQ behaviour (`maxReceiveCount = 3`) is unchanged.

## Image

- Tag `worker-f548bd0-runtime1`, digest
  `sha256:b41c778494574f09fa4e1072ec34ee73a4acd9f9d8e8c586b387cc16794fe06c`,
  linux/arm64, user `chordsync`. Built from `f548bd0` plus the S6-T11–S6-T13
  working tree. The guard2 Dockerfile is unchanged.
- ECR scan, 2026-10-11: 3 CRITICAL, 18 HIGH, 7 MEDIUM, 1 LOW, 1 UNDEFINED. The
  finding set is identical to guard2 and includes no new CRITICAL. The three
  exceptions were re-bound in `docs/security/container-exceptions.md`.
- Terraform `worker_image_digest` points to this digest. Task: FARGATE,
  LINUX/ARM64, 4 vCPU, 16 GiB, default 20 GiB ephemeral storage. New
  environment: `CHORDSYNC_MODEL_RELEASE=2026.10.1` and
  `CHORDSYNC_MODEL_MANIFEST_KEY=models/releases/2026.10.1/manifest.json`.
