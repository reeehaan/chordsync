# BTC checkpoint licensing decision

- Asset: BTC-ISMIR19 25-class checkpoint `btc_model.pt`
- Upstream: <https://github.com/jayg996/BTC-ISMIR19>, commit
  `2682317be668032e6e4b269ded36adaa2ad57df0`, file `test/btc_model.pt`
- SHA-256: `71c2c5db17e8c43b8a9a9da5db36ef2d667158c07a214eba16344c154c00bf54`
  (12,154,754 bytes)
- Decision date: 2026-10-11
- Decided by: ChordSync project owner
- Status: **APPROVED — NON-COMMERCIAL RESEARCH USE ONLY — PRIVATE AWS ACCOUNT**

## Decision

> Approved for non-commercial research use only, within ChordSync's private AWS
> account. The BTC checkpoint (`btc_model.pt`) is not redistributed, not
> bundled in the app, and not publicly accessible. The source keeps its MIT
> notice. Revisit before any public or commercial release.

## Basis

- BTC **source code** is MIT licensed (Copyright (c) 2019 Jonggwon Park). The
  MIT notice must accompany any copy of the source, including copies staged
  under the private `models/btc/source/` prefix.
- The MIT text covers "the Software" and does not mention the pretrained
  checkpoint. Upstream states no separate terms for the weights.
- The upstream README says the model was trained on Isophonics, Robbie
  Williams, and UsPop2002 chord labels, with audio "collected from online
  music service providers." The checkpoint is therefore derived from
  copyrighted recordings whose terms are unknown.
- This decision is the owner's acceptance of that uncertainty for a narrow,
  private, non-commercial research scope. It is not a finding that the
  checkpoint is MIT licensed or freely redistributable, and it is not legal
  advice.

## Conditions

1. Stored only in ChordSync's private AWS account: the private artifact bucket
   (Block Public Access, HTTPS-only) under `models/btc/checkpoints/<sha256>/`,
   and the ephemeral storage of worker tasks that load it.
2. Never committed to Git, bundled in the mobile app or any container image,
   published, shared, or served to users. Users receive only analysis results
   (chord timelines).
3. Read only by the worker task role (`s3:GetObject` on `models/*`).
4. Model manifests mark this asset `"license_status": "approved"`, which the
   worker bootstrap accepts. Other assets keep their own status.

## Re-review required before

- Any public release, or any use by people outside the project.
- Any commercial use, including paid features or monetisation.
- Any distribution of the checkpoint outside the private AWS account.
- Upstream publishing explicit terms for the weights.
