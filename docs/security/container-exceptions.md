# Container security exceptions

This record documents time-limited exceptions for scanner findings in the
ChordSync analysis worker. A scanner finding remains open unless a supported
package update removes it. An exception records runtime applicability and does
not claim that the CVE is fixed or absent from its source package.

## Scope and approval

- Bound image: `worker-f548bd0-runtime1` (S6-T13 runtime image)
- ECR digest: `sha256:b41c778494574f09fa4e1072ec34ee73a4acd9f9d8e8c586b387cc16794fe06c`
- ECR scan completed: 2026-10-11
- ECR scan result: 3 CRITICAL, 18 HIGH, 7 MEDIUM, 1 LOW, 1 UNDEFINED
- Previously bound image: `worker-24025ef0-guard2`
  (`sha256:9c027714e07bad4bb1916f364c04c5ea2ce8545d5be41babfecdcbcbd65f11c5`), superseded; see "Re-binding record" below.
- Owner: ChordSync project owner
- Approval status: **APPROVED — TIME-LIMITED — BOUND TO IMAGE DIGEST**
- Approval date: 2026-10-10
- Recorded: 2026-10-10
- Expires: 2026-11-09

The immutable candidate image contains the explicit local-path guard, including
the FFmpeg `subfile,,...,:...` defense-in-depth check. Exact-image container
tests rejected HTTP, HTTPS, S3, mixed-case, file, FTP, TCP, TLS, concat, pipe,
crypto, data, lavfi, subfile, malformed URI input, and URI output before a
subprocess could run. A synthetic local WAV completed ffprobe and preprocessing,
and its temporary workspace was removed. This exception approval does not by
itself authorize deployment.

All three scanner findings remain present. They are accepted only under the
documented, time-limited applicability exceptions for the exact image digest
above; none is represented as resolved or removed.

Deployment may proceed under these exceptions only after the project owner
explicitly approves them and confirms all of the following:

1. The TIFF finding remains inapplicable to functionality shipped in the
   runtime image.
2. FFmpeg and ffprobe remain restricted to local filesystem paths.
3. No supported GnuTLS fix is available.
4. The local-path and focused worker regression tests pass.
5. No other unresolved, runtime-applicable CRITICAL finding exists.

These exceptions require immediate re-review if Debian publishes a fixed
package, the base image changes, an FFmpeg or ffprobe invocation changes,
remote URLs become accepted, TIFF tooling is added, scanner evidence changes,
or the worker becomes public or multi-user.

## CVE-2026-52490 — TIFF tiffcrop

- Scanner severity: CRITICAL
- Bound image: `worker-f548bd0-runtime1`
- Bound ECR digest: `sha256:b41c778494574f09fa4e1072ec34ee73a4acd9f9d8e8c586b387cc16794fe06c`
- Scan date: 2026-10-11 (re-bound; first assessed 2026-10-10)
- Source package: `tiff`
- Installed binary package: `libtiff6:arm64 4.7.0-3+deb13u3`
- Affected functionality: command processing in `tools/tiffcrop.c`
- Runtime presence: the source-package finding is present, but `tiffcrop`,
  `tiff-tools`, and `libtiffxx6` are not installed. Only the shared `libtiff6`
  runtime library is installed.
- Runtime reachability: **NOT_APPLICABLE** based on current evidence. The
  affected executable and command-line functionality are not shipped, and no
  ChordSync subprocess invokes TIFF command-line tools.
- Attacker control: uploaded audio can reach supported audio decoders, but it
  cannot invoke the absent `tiffcrop` executable or its command parser.
- Dependency reason: the supported Debian FFmpeg graph retains `libtiff6` via
  `libavcodec61 -> librsvg2-2 -> libgdk-pixbuf-2.0-0 -> libtiff6`.
- Supported fix availability: no fixed package exists in stable Debian Trixie.
  Debian records Trixie `4.7.0-3+deb13u3` as vulnerable and `4.7.2-1` as fixed
  only in testing/unstable.
- Compensating controls: TIFF CLI packages are absent; the container runs as a
  non-root user; subprocess arguments are fixed lists; no shell is used; and
  adding TIFF tooling triggers immediate review.
- Exception rationale: the scanner maps a source-package issue to a runtime
  shared-library package even though the specifically affected executable and
  function are not present. The library cannot currently be removed without
  departing from the supported FFmpeg dependency graph.
- Owner: ChordSync project owner
- Guard test evidence: the exact image rejected all tested URI/protocol inputs
  and outputs before subprocess execution and accepted a synthetic local WAV.
- Approval status: **APPROVED — TIME-LIMITED — BOUND TO IMAGE DIGEST**
- Approval date: 2026-10-10
- Review triggers and expiration: the common triggers above; 2026-11-09.

Evidence commands:

```text
dpkg-query -W libtiff6
dpkg-query -W tiff-tools libtiffxx6
command -v tiffcrop
rg -n 'tiffcrop|tiffinfo|tiffdump|tiffset|tiffsplit|tiffcp' backend analysis
```

Authoritative status:
<https://security-tracker.debian.org/tracker/CVE-2026-52490>

## CVE-2026-95210 — GnuTLS certificate validation

- Scanner severity: CRITICAL
- Bound image: `worker-f548bd0-runtime1`
- Bound ECR digest: `sha256:b41c778494574f09fa4e1072ec34ee73a4acd9f9d8e8c586b387cc16794fe06c`
- Scan date: 2026-10-11 (re-bound; first assessed 2026-10-10)
- Source package: `gnutls28`
- Installed binary package: `libgnutls30t64:arm64 3.8.9-3+deb13u4`
- Affected functionality: certificate validation in GnuTLS.
- Runtime presence: **PRESENT**. Both FFmpeg and ffprobe dynamically link
  `libgnutls.so.30`, and their builds expose HTTP/HTTPS protocols.
- Runtime reachability: **NOT_APPLICABLE UNDER THE CURRENT WORKER FLOW**.
  Worker source objects are first materialized into a per-job local file.
  Preprocessing then passes that local path to FFmpeg and ffprobe. Repository
  code now also rejects HTTP, HTTPS, other URI schemes, and malformed URI-style
  values before a subprocess can start; that guard must be included in the
  eventual deployment image as described in the scope note.
- Attacker control: users control uploaded audio bytes but cannot supply an
  FFmpeg/ffprobe network URL or arbitrary command-line options. Commands use
  fixed argument lists and never use a shell.
- Model downloads: WhisperX, alignment-model, and Demucs downloads use their
  Python libraries and Python TLS stack. They do not pass model URLs to FFmpeg
  or ffprobe. This networking is separate from the GnuTLS-backed path covered
  by this exception.
- Supported fix availability: Debian currently records the issue as unfixed in
  Bookworm, Trixie, testing, and unstable. No supported Debian fixed package is
  available.
- Compensating controls: local-path validation; source materialization before
  analysis; fixed subprocess argument construction; no `shell=True`;
  non-root execution; and focused regression tests for URI rejection.
- Exception rationale: the library and scanner finding are materially present,
  but the affected certificate-validation path is not reachable through the
  current local-file-only FFmpeg workflow. The exception is valid only while
  that invariant remains enforced.
- Owner: ChordSync project owner
- Guard test evidence: the exact image rejected HTTP, HTTPS, S3, arbitrary
  tested URI schemes, malformed URI input, and URI output before FFmpeg,
  ffprobe, or any subprocess could start; local synthetic audio succeeded.
- Approval status: **APPROVED — TIME-LIMITED — BOUND TO IMAGE DIGEST**
- Approval date: 2026-10-10
- Review triggers and expiration: the common triggers above; 2026-11-09.

Evidence commands:

```text
dpkg-query -W libgnutls30t64
ldd /usr/bin/ffmpeg | grep libgnutls
ldd /usr/bin/ffprobe | grep libgnutls
ffmpeg -hide_banner -protocols
rg -n 'http://|https://|ffmpeg|ffprobe|subprocess|Popen|run\(' backend analysis
```

Authoritative status:
<https://security-tracker.debian.org/tracker/CVE-2026-95210>

## CVE-2026-88647 — GnuTLS hostname verification

- Scanner severity: CRITICAL
- Bound image: `worker-f548bd0-runtime1`
- Bound ECR digest: `sha256:b41c778494574f09fa4e1072ec34ee73a4acd9f9d8e8c586b387cc16794fe06c`
- Scan date: 2026-10-11 (re-bound; first assessed 2026-10-10)
- Source package: `gnutls28`
- Installed binary package: `libgnutls30t64:arm64 3.8.9-3+deb13u4`
- Affected operation: `gnutls_x509_crt_check_hostname2()` can fall back to a
  certificate Common Name when the certificate contains only unsupported SAN
  types, such as URI SAN. A crafted certificate can therefore pass hostname
  identity verification under the affected conditions.
- Runtime linkage: **PRESENT**. Both FFmpeg and ffprobe dynamically link
  `libgnutls.so.30`, and their builds expose GnuTLS-backed HTTPS/TLS protocols.
- Runtime reachability: **PRESENT BUT NOT RUNTIME REACHABLE UNDER THE CURRENT
  WORKER FLOW**. Object-storage audio is materialized as a fixed local
  `input.wav`, `input.mp3`, or `input.m4a` path before analysis. All
  FFmpeg/ffprobe call sites receive materialized or worker-generated local
  paths, not source URLs.
- Attacker control: an attacker would need to make FFmpeg/ffprobe initiate TLS
  to an attacker-controlled endpoint and present a crafted certificate that
  chains to a trusted anchor. Uploaded bytes do not control the subprocess
  argument path or select a network endpoint in the current worker flow.
- URI guard evidence: HTTP, HTTPS, S3, arbitrary standard URI schemes,
  malformed URI forms, protocol-prefixed input, and URI-style output are
  rejected before subprocess execution. Review found that FFmpeg's special
  `subfile,,...,:...` syntax bypassed the original `urlsplit()`-only check. The
  bound image rejects that syntax and has focused regression coverage. Exact
  image validation confirmed every rejected case failed before subprocess
  execution and a normal local WAV remained accepted.
- Fix availability: no supported fix is currently available. Debian marks
  Bookworm, Trixie, Forky, and Sid vulnerable and records the fixed version as
  `(unfixed)`.
- Compensating controls: storage materialization to fixed filenames;
  worker-generated local output paths; fixed subprocess argument arrays; no
  shell execution; explicit URI/protocol rejection; non-root execution; and
  focused regression tests.
- Owner: ChordSync project owner
- Approval status: **APPROVED — TIME-LIMITED — BOUND TO IMAGE DIGEST**
- Approval date: 2026-10-10
- Existing exception expiration: 2026-11-09
- Re-review triggers: a Debian or upstream fix; base, FFmpeg, GnuTLS, or worker
  image change; any FFmpeg/ffprobe call-site change; acceptance of remote or
  caller-selected paths; URI-guard changes; new scanner evidence; or public or
  multi-user worker exposure.

Authoritative status:
<https://security-tracker.debian.org/tracker/CVE-2026-88647>

Upstream behavior:
<https://gitlab.com/gnutls/gnutls/-/issues/1802>

## Re-binding record

### 2026-10-11 — `worker-24025ef0-guard2` → `worker-f548bd0-runtime1`

The three exceptions above were re-bound to the S6-T13 runtime image without
any change to their scope, rationale, approval date, or 2026-11-09 expiry.

- New digest: `sha256:b41c778494574f09fa4e1072ec34ee73a4acd9f9d8e8c586b387cc16794fe06c` (linux/arm64, user `chordsync`)
- Image changes: S6-T13 model bootstrap (private S3 manifest download with
  SHA-256 verification before queue polling), SQS visibility heartbeat, and the
  previously reviewed refactor commits up to `f548bd0`. Same Dockerfile, base
  images, and Debian packages as guard2.
- Scan evidence: ECR scan COMPLETE 2026-10-11. The full finding set (30
  findings: severity, CVE, package, and version) is identical to guard2. The
  same three CRITICAL findings remain; no new CRITICAL or HIGH finding.
- FFmpeg/ffprobe applicability: no FFmpeg, ffprobe, or subprocess call site
  changed between guard2's source and this image. The URI guard is unchanged.
- New network I/O: the model bootstrap reads S3 through boto3 and the Python
  `ssl` module, which uses OpenSSL 3.5.7 in this image, not GnuTLS. It does not
  invoke FFmpeg/ffprobe, so it does not create a path to the GnuTLS findings.
- Exact-image validation (offline, `--network none`): non-root; ffmpeg and
  ffprobe present; backend, BTC, madmom, WhisperX, and Demucs environments
  import with CPU fallback; worker and consumer CLIs; URI guard rejected HTTP,
  HTTPS, S3, file, FTP, TCP, TLS, concat, pipe, crypto, data, lavfi, and
  `subfile,,` inputs and URI output; synthetic model bootstrap installed into
  the approved paths, rejected a tampered asset with exit code 3, and never
  built or polled the queue consumer on failure.

## Security gate

The deployment gate is **zero unresolved, runtime-applicable CRITICAL
findings**. Scanner CRITICAL findings are never silently ignored: each accepted
finding requires current applicability evidence, compensating controls, an
owner, explicit approval, and an unexpired review date. Expired, unapproved,
or newly runtime-reachable findings are unresolved and block deployment.
