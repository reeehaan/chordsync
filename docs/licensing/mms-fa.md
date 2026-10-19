# MMS forced-alignment weights licensing decision

- Asset: Meta MMS CTC alignment model used by `torchaudio.pipelines.MMS_FA`
  (`ctc_alignment_mling_uroman`), file `model.pt`
- Upstream: downloaded from
  `https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt`
  (torchaudio 2.8.0)
- SHA-256: `20ef12963ab4924bef49ac4fc7f58ad5da2ee43b2c11bc8c853c9b90ecdbc680`
  (1,262,047,414 bytes)
- Decision date: 2026-10-19
- Decided by: ChordSync project owner
- Status: **APPROVED, NON-COMMERCIAL RESEARCH USE ONLY, PRIVATE AWS ACCOUNT**

## What it is used for

Aligning the correct, time-synced lyrics of songs in languages without a WhisperX
aligner (for example Sinhala and Hindi) to the vocals, so each word has a real
start and end time (`analysis/lyrics/mms_alignment.py`). The audio never leaves
the worker. The lyrics are romanised with `uroman` 1.3.1.1 (Apache-2.0, pure
Python) only to match the model's alphabet.

## Basis

- Meta's MMS release states its code and model weights are CC-BY-NC 4.0, which
  does not allow commercial use. This should be re-checked against the upstream
  repository before any public or commercial release.
- The weights are not redistributed, not bundled in the app or an image, and not
  publicly accessible; they are installed from the private artifacts bucket by the
  model bootstrap (optional role `alignment_mms`, release `2026.10.2`).

## Decision

Approved by the project owner ("I'm using it for non-commercial research") on the same terms as the BTC checkpoint
(`docs/licensing/btc-checkpoint.md`) and the Demucs weights
(`docs/licensing/demucs-htdemucs.md`): non-commercial research use only, within
ChordSync's private AWS account. Revisit before any public or commercial release
(the aligner is optional; with it disabled, words are spread evenly inside each
line).
