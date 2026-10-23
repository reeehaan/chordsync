# BTC large-vocabulary checkpoint licensing decision

- Asset: BTC-ISMIR19 170-chord checkpoint `btc_model_large_voca.pt`
- Upstream: <https://github.com/jayg996/BTC-ISMIR19>, commit
  `2682317be668032e6e4b269ded36adaa2ad57df0`, file `test/btc_model_large_voca.pt`
  (git blob `11c6edbaaaee33737aa7a41dcb9044191630326f`, the same commit as the
  25-class checkpoint)
- SHA-256: `1673d23f8f9a55ae7f9e8b80a51da616debb22675b8d8b67ea6ce0ef37b0ab51`
  (12,229,576 bytes)
- Decision date: 2026-10-23
- Decided by: ChordSync project owner, who instructed its deployment to the
  private AWS account (the decision for the 25-class checkpoint is in
  `docs/licensing/btc-checkpoint.md`)
- Status: **APPROVED — NON-COMMERCIAL RESEARCH USE ONLY — PRIVATE AWS ACCOUNT**

## Decision

> Approved for non-commercial research use only, within ChordSync's private AWS
> account, on the same terms as the 25-class checkpoint. The large-vocabulary
> checkpoint is not redistributed, not bundled in the app or in any container
> image, and not publicly accessible. Revisit before any public or commercial
> release.

## Basis

This is the same upstream project, commit and licensing position as
`btc_model.pt`:

- BTC **source code** is MIT licensed. The MIT text covers "the Software" and
  does not mention the pretrained weights, and upstream states no separate terms
  for them.
- The upstream README says the models were trained on chord labels whose audio
  was "collected from online music service providers", so the weights derive from
  recordings whose terms are unknown.
- This decision is the owner's acceptance of that uncertainty for a narrow,
  private, non-commercial research scope. It is not a finding that the checkpoint
  is MIT licensed or freely redistributable, and it is not legal advice.

## What it is used for

Only the optional chord-extensions step (`analysis/chords/extensions.py`). The
model labels each song with 170 chords; ChordSync keeps a label only where it
agrees with a check of the notes actually sounding, and only for the 7, maj7, m7,
sus2 and sus4 chords. Users receive analysis results (chord timelines), never the
model.

## Conditions

1. Stored only in ChordSync's private AWS account: the private artifact bucket
   (Block Public Access, HTTPS-only) under `models/btc/checkpoints/<sha256>/`,
   and the ephemeral storage of worker tasks that load it.
2. Never committed to Git, bundled in the mobile app or any container image,
   published, shared, or served to users.
3. Read only by the worker task role (`s3:GetObject` on `models/*`).
4. The manifest (release 2026.10.3 and later) marks this asset
   `"license_status": "approved"` and `"required": false`: workers fetch it on
   demand and only when chord extensions are switched on.

## Re-review required before

- Any public release, or any use by people outside the project.
- Any commercial use, including paid features or monetisation.
- Any distribution of the checkpoint outside the private AWS account.
- Upstream publishing explicit terms for the weights.
