# S7-T08 preparation: image provenance

The API image for the hosted deployment is rebuilt from the committed S7
checkpoint, replacing the one built from uncommitted source in S7-T07.

```
Git commit 2ed4afa  ->  clean export (git archive)  ->  docker build (linux/arm64)
  ->  ECR api-2ed4afa-s7  ->  digest in Terraform plan  ->  deployed Lambda
```

| | |
| --- | --- |
| Git commit | `2ed4afafda35a51f405ff928d70fbff4e85eb7fc` (`feat: prepare hosted cloud API`) |
| Build input | `git archive` of that commit, so no working-tree or untracked file can enter the image |
| Local tag / ID | `chordsync-api:s7t08` / `sha256:e98c9062951e534cd152e1a967db77c13770665810fd02b12d82f42297f90dc1` |
| ECR tag | `api-2ed4afa-s7` (immutable) |
| ECR digest | `sha256:bc9b30b6d5d87006bdac420e5614c747ac91e24598f11addb53f6efe073e82ca` |
| Size | 72,039,570 bytes in ECR; about 70.4 MB compressed, 196.2 MB uncompressed |
| Platform / manifest | linux/arm64, Docker v2 manifest, user 10001 |
| ECR scan | complete 2026-10-16: CRITICAL 0, HIGH 3, MEDIUM 9, LOW 3 (same findings as before: glibc x2 HIGH, zlib HIGH; Docker Scout 0C/1H/1M/26L) |

`api-s7t07-runtime1` (digest `sha256:cdfaf6c6…c982e`) remains in ECR, untouched,
and is **superseded**: it was built from uncommitted source. It also carried
three untracked test files from the working tree (`analysis/fusion/test_real_timeline_lookup*.py`,
`analysis/lyrics/test_whisper_runner.py`) that the clean build does not. Every
other file under `/app` is byte-identical between the two images. Do not deploy
the old digest; the old tag can be removed in a cleanup ticket (ECR tags are
immutable, so it cannot be moved).

Repeated local checks on the new image (closed AWS endpoint, fake credentials):
`/` 200, `/health` 200, create and status without a token 401 with
`WWW-Authenticate: Bearer`, create with a token and unreachable SSM 503, `/docs`,
`/openapi.json` and the legacy upload 404; uid 10001, read-only root, `/tmp`
writable, no ffmpeg or Mutagen, and no plaintext token in the image or its
environment.

## Final plan inputs and result

`hosted_api_enabled=true`, `api_image_digest=sha256:bc9b30b6…e82ca`,
`demo_token_parameter_name=/chordsync/demo/auth/token-verifiers`,
`api_reserved_concurrency=-1`, `dispatcher_enabled=true`,
`dispatcher_schedule_enabled=true`. Saved plan (session scratch, not applied):
`/private/tmp/claude-501/-Users-rehan-Documents-ChordSync/de742a01-ff90-4b4e-a5e4-d8bd3a744be7/scratchpad/final-hosted-2ed4afa.tfplan`.

**22 to add, 1 to change, 0 to destroy; no warnings, no replacements.** It is the
same resource and action set as the S7-T07 plan; the only attribute that differs
is the API function's `image_uri`. The dispatcher zip (built from the clean
export too) is byte-identical to the S7-T07 one: SHA-256
`e477a4bee54870a161e0c3af7d1c4036f28fdafe47b8276b5529daccbbd6ec06`. No plaintext
token appears in the plan text, JSON, or binary plan. Deployed paths
(`infrastructure`, `backend`, `scripts`, `analysis`) match the commit exactly.

Not committed: `README.md` and `docs/development-setup.md`, as instructed. This
file is also uncommitted.
