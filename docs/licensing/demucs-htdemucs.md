# Demucs htdemucs weights licensing decision

- Asset: Demucs `htdemucs` pretrained weights, `955717e8-8726e21a.th`
- Upstream: <https://github.com/facebookresearch/demucs> (demucs 4.0.1),
  downloaded from
  `https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th`
- SHA-256: `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`
  (84,141,911 bytes). Byte-identical to the upstream download (S3 multipart
  ETag `717b8271e7f909c2395df6c94a03b50a-6` recomputed locally).
- Decision date: 2026-10-12
- Decided by: ChordSync project owner
- Status: **APPROVED — NON-COMMERCIAL RESEARCH USE ONLY — PRIVATE AWS ACCOUNT**

## Decision

Approved for non-commercial research use only, within ChordSync's private AWS
account, on the same terms as the BTC checkpoint
(`docs/licensing/btc-checkpoint.md`). The weights are not redistributed, not
bundled in the app or any image, and not publicly accessible. Revisit before
any public or commercial release.

## Basis

- The Demucs README states "Demucs is released under the MIT license as found
  in the LICENSE file" (Copyright (c) Meta Platforms, Inc. and affiliates). It
  does not name the pretrained weights separately.
- The README states `htdemucs` was "trained on MusDB + 800 songs". MUSDB18-HQ
  is distributed for non-commercial research, and the terms of the additional
  800 songs are not published.
- This is the owner's acceptance of that uncertainty for a narrow, private,
  non-commercial research scope. It is not a finding that the weights are MIT
  licensed or freely redistributable, and it is not legal advice.

## Conditions and re-review

The conditions and re-review triggers are the same as for the BTC checkpoint:
private S3 and worker ephemeral storage only, read only by the worker task
role, manifest `"license_status": "approved"`, and re-review before any public
release, commercial use, distribution outside the private AWS account, or if
upstream publishes terms for the weights.
