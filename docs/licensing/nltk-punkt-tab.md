# NLTK punkt_tab licensing decision

- Asset: NLTK `punkt_tab` (Punkt sentence-tokenizer parameters, tabular
  format), required by WhisperX word alignment
- Upstream: <https://github.com/nltk/nltk_data>, branch `gh-pages`, commit
  `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`, file
  `packages/tokenizers/punkt_tab.zip`
- SHA-256: `e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106`
  (4,319,076 bytes). The MD5 `27ea9ee08fe27fe4484e4c5585cce748` matches the
  official NLTK data index entry.
- Format: plain-text tables (no pickled code)
- Decision date: 2026-10-13
- Decided by: ChordSync project owner
- Status: **APPROVED — NON-COMMERCIAL RESEARCH USE ONLY — PRIVATE AWS ACCOUNT**

## Decision

Approved for non-commercial research use only. The exact pinned archive above
is baked into the private ChordSync worker image, which is stored only in the
project's private ECR repository and runs only in its private AWS account. It
is not redistributed, not bundled in the mobile app, and not publicly
accessible. Revisit before any public or commercial release.

## Basis

- The NLTK data index lists no licence for `punkt_tab`, and the package README
  states no terms.
- The README credits Jan Strunk and Tibor Kiss (Kiss and Strunk, 2006). The
  English model was trained on the Wall Street Journal portion of the Penn
  Treebank (LDC); other languages were trained on various newspaper corpora.
- This is the owner's acceptance of that uncertainty for a narrow, private,
  non-commercial research scope, consistent with the BTC checkpoint and Demucs
  decisions. It is not a finding that the data is freely redistributable, and
  it is not legal advice.

## Conditions and re-review

Same as `docs/licensing/btc-checkpoint.md`. Re-review is required before any
public release, commercial use, distribution of the image or data outside the
private AWS account, or if upstream publishes terms.
