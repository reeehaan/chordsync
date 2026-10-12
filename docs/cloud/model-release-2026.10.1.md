# Model release 2026.10.1

Private model assets for the analysis worker, staged in the artifact bucket
and installed by the worker bootstrap
(`docs/cloud/s6-t13-model-bootstrap.md`). The exact manifest is committed at
`infrastructure/models/releases/2026.10.1/manifest.json` and stored at
`models/releases/2026.10.1/manifest.json`. The two are byte-identical
(SHA-256 `ecb88b943efb62545326168ee47a56ecef91e56d0d8b6242f9e2ad49f6bfa894`).
The manifest lists the key, size, and SHA-256 of all 15 files.

- Staged: 2026-10-12
- Assets: 15 files, 960,220,509 bytes, all five required roles
- Bucket: private artifact bucket (Block Public Access, SSE-S3, HTTPS-only)

## Staging and verification

1. Every asset was verified against its upstream source (below) before upload.
2. The production bootstrap installed this exact manifest from local copies
   into the image's file layout. Every model then loaded offline from that
   layout: faster-whisper, torchaudio wav2vec2, Demucs `htdemucs` (with its own
   hash check), and BTC on CPU. No song was analysed.
3. Each asset was uploaded with an S3-verified SHA-256 checksum, SSE-S3
   encryption, and `If-None-Match: *`, so no object could be overwritten.
4. All 15 assets were downloaded back from S3 and re-hashed: SHA-256, size,
   S3-stored checksum, and encryption matched for every file.
5. The manifest was uploaded last, read back byte-for-byte, and accepted by the
   worker's production manifest parser.

Staging uploaded objects to S3 only. No Terraform was applied, no ECS, Fargate,
or EC2 compute was started, and no song was analysed.

## Assets and provenance

| Role | Asset | Upstream verification | Licence | Status |
| --- | --- | --- | --- | --- |
| `btc_source` | BTC-ISMIR19 source: `LICENSE`, `run_config.yaml`, `btc_model.py`, `utils/__init__.py`, `utils/hparams.py`, `utils/mir_eval_modules.py`, `utils/transformer_modules.py` | Commit `2682317be668032e6e4b269ded36adaa2ad57df0` is upstream `master`. 4 files are unmodified; 3 carry the patch below. | MIT (`LICENSE` staged with the code) | `permissive` |
| `btc_checkpoint` | `btc_model.pt`, SHA-256 `71c2c5db17e8c43b8a9a9da5db36ef2d667158c07a214eba16344c154c00bf54`, 12,154,754 bytes | Git blob `6b4d7f796998cb22822e33468d66394e176ee33a`, identical to the upstream commit | No terms stated for the weights | `approved`, non-commercial research only, private AWS account (`docs/licensing/btc-checkpoint.md`) |
| `whisperx_asr` | `Systran/faster-whisper-small` rev `536b0662742c02347bc0e980a01041f333bce120`: `refs/main`, `config.json`, `model.bin`, `tokenizer.json`, `vocabulary.txt` | Hugging Face API: `model.bin` LFS SHA-256 `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671` (483,546,902 bytes), and the other files' Git blob IDs match. The revision is current `main`. | MIT (model card) | `permissive` |
| `alignment_en` | `wav2vec2_fairseq_base_ls960_asr_ls960.pth`, SHA-256 `488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d`, 377,664,473 bytes | Byte-identical to `download.pytorch.org/torchaudio/models/` (multipart ETag `ac14bf300dff9b8d21560e4a1a465d36-23` recomputed) | MIT. torchaudio states the weights are published and redistributed under MIT. | `permissive` |
| `demucs_htdemucs` | `955717e8-8726e21a.th`, SHA-256 `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`, 84,141,911 bytes | Byte-identical to `dl.fbaipublicfiles.com/demucs/hybrid_transformer/` (multipart ETag `717b8271e7f909c2395df6c94a03b50a-6` recomputed) | Code MIT; weights not named; trained on MUSDB HQ + 800 songs | `approved`, non-commercial research only, private AWS account (`docs/licensing/demucs-htdemucs.md`) |

## BTC source patch

`analysis/chords/btc/patches/btc-ismir19-compat.patch` (SHA-256
`69fc2f81b1e26147e18fb32aa922ff197039b12500fd85de4bc057c63c54b637`) applies
cleanly to upstream commit `2682317b`. The result is byte-identical to the
three staged files. It makes three changes:

1. `utils/hparams.py`: `yaml.load` → `yaml.safe_load`, required by current
   PyYAML.
2. `utils/transformer_modules.py`: `np.float` → `float`. The alias was removed
   from NumPy.
3. `utils/mir_eval_modules.py`: `audio_file_to_features` starts its CQT
   feature buffer as `None` instead of relying on `start_idx == 0`.

Change 3 does not alter the algorithm. On a 25-second synthetic tone, original
and patched feature extraction were identical. On a 3-second tone (shorter
than the 10-second analysis window), the original raised `UnboundLocalError`
and the patched code returned features. The chord model, vocabulary, and
inference are unchanged.

## Not staged

- WhisperX VAD: bundled in whisperx 3.8.6 inside the image. It is identical
  (SHA-256 `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`,
  17,719,103 bytes) to `pytorch_model.bin` in the official
  `pyannote/segmentation` repository, which is MIT licensed. That repository
  is gated by contact-sharing conditions.
- madmom models: bundled in the madmom 0.16.1 package inside the image.
- Non-English alignment models.

## Scope

The BTC source is MIT licensed. The BTC checkpoint and the Demucs weights are
approved only for non-commercial research use within ChordSync's private AWS
account, by explicit project-owner decisions. This release grants no
redistribution or commercial rights, and MIT does not automatically apply to
either set of weights. It must not be made public, bundled into the app, or
used commercially without re-reviewing both decisions.
