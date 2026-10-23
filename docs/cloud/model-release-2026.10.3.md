# Model release 2026.10.3

Release 2026.10.3 is release 2026.10.2 plus one optional, on-demand asset: the
BTC-ISMIR19 170-chord checkpoint, role `btc_large_checkpoint`. It is used only by
the chord-extensions step (`docs/cloud/chord-extensions.md`). The manifest is
committed at `infrastructure/models/releases/2026.10.3/manifest.json` and stored
in the private artifact bucket. The two are byte-identical (SHA-256
`cbf743df351ebca47b9b47398a52eed8f702edc631fd0583ffc8ba1de82cc093`). The
Terraform default for the model release is 2026.10.3 (commit `257f018`).

- Staged: 2026-10-23
- Added asset: 1 file, 12,229,576 bytes, optional (`"required": false`)
- Bucket: private artifact bucket (Block Public Access, SSE-S3, HTTPS-only)
- Earlier releases: `2026.10.1` (`docs/cloud/model-release-2026.10.1.md`) and
  `2026.10.2` are untouched.

## The new asset

| Field | Value |
| --- | --- |
| Role | `btc_large_checkpoint` |
| File | `btc_model_large_voca.pt` |
| SHA-256 | `1673d23f8f9a55ae7f9e8b80a51da616debb22675b8d8b67ea6ce0ef37b0ab51` |
| Size | 12,229,576 bytes |
| Upstream | BTC-ISMIR19 commit `2682317be668032e6e4b269ded36adaa2ad57df0`, file `test/btc_model_large_voca.pt` |
| Git blob | `11c6edbaaaee33737aa7a41dcb9044191630326f`, identical to the local upstream checkout |
| Bucket key | `models/btc/checkpoints/<sha256>/btc_model_large_voca.pt` |
| Licence status | `approved`, non-commercial research only, private AWS account (`docs/licensing/btc-large-checkpoint.md`) |

The first 6 assets of the manifest are byte-identical to 2026.10.2. A test pins
this.

## Staging and verification

1. The checkpoint was uploaded with an S3-verified SHA-256 checksum, SSE-S3
   encryption, and `If-None-Match: *`. A second upload of the same key was refused
   with `PreconditionFailed`.
2. The object was read back and re-hashed: it matches.
3. The manifest was uploaded last, read back byte-identical, and accepted by the
   worker's production manifest parser.
4. Both objects were also copied to the protected model backup bucket and
   re-hashed there.

## Installation

The worker installs the file beside `btc_model.pt` as `btc_model_large_voca.pt`.
The role is in `ON_DEMAND_ROLES` (`backend/api/app/services/model_bootstrap.py`),
so it is never installed at startup. The chord-extensions step fetches and
verifies it just before it runs, as the MMS aligner is fetched for lyrics
(`docs/cloud/s8-t03-reference-lyrics-and-cancel.md`).

## Proof on the real worker

Job `633ccd39-32df-4764-b8d7-0d1bbb82489e`:

| Moment | Log line |
| --- | --- |
| Startup | `model bootstrap release=2026.10.3 installed=15 already_present=0 verified_bytes=960220509` |
| On demand | `installed=1 verified_bytes=12229576` |

Startup installs the same 15 files and 960,220,509 bytes as release 2026.10.1.

## Scope

The checkpoint is approved only for non-commercial research use within
ChordSync's private AWS account, by an explicit project-owner decision. It must
not be made public, bundled into the app or an image, or used commercially without
re-review (`docs/licensing/btc-large-checkpoint.md`).
