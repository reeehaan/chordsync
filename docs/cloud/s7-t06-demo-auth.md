# S7-T06 Demo-token authentication and ownership

The hosted API now requires `Authorization: Bearer <demo-token>` on every
`/analysis/*` route, and every job belongs to the principal that created it.
Nothing is deployed or applied; the SSM parameter does not exist yet.

## Routes

| Route | Hosted | Local |
| --- | --- | --- |
| `GET /health` | public | public |
| `GET /` | public (name and "running" only) | public |
| `POST /analysis/jobs`, `POST …/confirm-upload`, `GET …/{id}`, `GET …/{id}/result` | **authenticated** | open, unless auth is configured |
| `/docs`, `/redoc`, `/openapi.json` | not served (hosted) | served |
| legacy `POST /api/v1/audio/upload` | not registered | unchanged |

Protection is a router-level dependency, so a route added later is covered too.
Local development is unchanged unless `CHORDSYNC_DEMO_TOKEN_VERIFIER` (inline
document) or `CHORDSYNC_DEMO_TOKEN_PARAMETER` is set; local jobs themselves are
not owner-scoped (the in-memory local service has no owner field).

## Token model

- The client sends a random 256-bit token. It is never in the repository, the
  image, a response, a job record, an S3 key, a job ID, a URL, or a log.
- The server stores only SHA-256 verifiers. A plain SHA-256 is right for a
  256-bit random secret (it is not a password).
- Verification hashes the presented token and compares it with every entry using
  `hmac.compare_digest`, with no early exit, so timing reveals neither which
  entry nor how much matched.
- Header handling is strict and uniform: missing header, other scheme, empty or
  blank token, extra parts, odd characters, and implausible lengths (16–256) all
  raise the same error.
- `scripts/generate_demo_token.py --id tester-1` creates tokens (printed once to
  stderr) and the verifier document (stdout); it never contacts AWS. Standard
  library only; no auth dependency was added.

Verifier document (the SSM parameter value):

```json
{"version": 1, "tokens": [{"id": "tester-1", "sha256": "<64 lowercase hex>"}]}
```

Labels match `[a-z0-9][a-z0-9-]{0,31}`, are unique, at most 50 entries, at most
8 KB. Any defect is an infrastructure fault (503), and the error never repeats
the document.

## SSM design

- `CHORDSYNC_DEMO_TOKEN_PARAMETER` names a **SecureString** parameter, read with
  `ssm:GetParameter` and decryption, on exactly that name. Terraform never
  creates or reads it (so the verifier stays out of state); create it by hand
  before deployment.
- Hosted mode **refuses to start** without the variable
  (`HostingConfigurationError`); it never falls back to "no auth". A hosted app
  with no verifier source answers 503. An inline verifier is ignored when hosted.
- **Caching:** the document is loaded once per warm environment and cached for
  5 minutes (so a rotated token takes effect without a cold start), not fetched
  per request. If a refresh fails, the last good verifier keeps serving and the
  failure is logged. With nothing loaded yet, a failure raises "unavailable" and
  is remembered for 5 s so a broken parameter is not hammered. Concurrent first
  requests cause one load.
- **Failures are 503, never 401:** load failure, throttling, a missing
  parameter, and a malformed value all return
  `503 service_unavailable`; the cause is only in the server log (error type, no
  value).

## Principal abstraction (Cognito seam)

`AuthenticatedPrincipal(principal_id)` and the `TokenVerifier` /
`VerifierProvider` protocols live in `backend/api/app/auth.py`. Routes use one
dependency, `get_principal`, and pass `principal_id` on as `owner_id`; they
reference no demo-token detail (a test enforces that). To move to Cognito: add a
JWT verifier that returns `AuthenticatedPrincipal("cognito:<sub>")`, swap the
provider in `_auth_provider`, and let API Gateway's JWT authorizer or the
verifier validate tokens. Job routes, ownership checks, and the `owner_id`
column stay as they are. Not implemented here.

## Ownership

- `owner_id` is `demo:<id>`: the operator's label for the token, stable across
  requests and rotations of the token, non-secret, and not derived from the
  token. The plaintext token is never an owner ID.
- **Create** records the owner (a hosted create without one is refused).
  **Confirm, status, and result** require `job.owner_id == principal_id`.
- Another owner's job, and a job with no owner (anything created before auth),
  look exactly like a missing one: `404 job_not_found`, same body, never 403.
  The check runs before any state change, S3 call, or SQS message, so a
  cross-owner request cannot observe, claim, confirm, or dispatch anything.
- The S3 key stays server-generated from the job ID; no credential is encoded in
  keys, URLs, IDs, or logs.
- Idempotency is unchanged for the owner (first confirm 202, repeats 200, one
  SQS message). A different principal gets 404 even after dispatch.
- The dispatcher stays internal: no bearer logic, no principal, no import of the
  API package. The API invokes it with its Lambda role (IAM), asynchronously.

## 401 vs 404 vs 503

| Situation | Response |
| --- | --- |
| no header, wrong scheme, empty, malformed, unknown or near-miss token | `401` `{"error":{"code":"unauthorized","message":"Authentication required."}}` with `WWW-Authenticate: Bearer`; identical for every cause |
| valid token, someone else's (or an ownerless, or no such) job | `404 job_not_found` |
| verifier unreachable, parameter missing, value malformed | `503 service_unavailable` |

Authentication runs before body parsing, so an unauthenticated caller gets 401
even for a malformed body or odd job ID.

## Terraform (design only)

- `hosted_api_acknowledge_no_auth` is **removed**. The plan now fails unless
  `demo_token_parameter_name` is set (preconditions on the gateway and the
  Lambda). The Lambda gets `CHORDSYNC_DEMO_TOKEN_PARAMETER`.
- API role adds `ssm:GetParameter` on that one parameter's ARN (no path, wildcard,
  `GetParametersByPath`, or Secrets Manager). For a SecureString encrypted with
  the default `alias/aws/ssm` key, no KMS permission is needed. If a
  customer-managed key is used, set `demo_token_kms_key_arn` to add `kms:Decrypt`
  on that key only, conditioned on `kms:ViaService = ssm.<region>.amazonaws.com`.
- **`s3:ListBucket`, narrow:** the API role gets it on the **bucket ARN only**
  with `StringLike s3:prefix = jobs/*/source/*`, so a HEAD for an absent source
  key can return a real 404. It is not `IfExists` (that would fail open for
  unprefixed listings), not on objects, and not unrestricted. **This is
  unverified against real S3**: if the HEAD authorization does not carry
  `s3:prefix`, the condition will not match and a missing key stays a 403.
  The behavior is safe either way: a 404 is `upload_not_received` (or
  `upload_expired`), and a 403 is a configuration fault reported as 503. The
  deployment smoke test must try an early confirm; if it returns 503, the fall-back
  options are in the S7-T05 document.
- **Lambda concurrency:** `api_reserved_concurrency` defaults to **-1** (no
  reservation). 0 is rejected (it blocks every call); positive values are accepted
  for after a quota increase and trip a warning only if they would leave under 10
  unreserved. The account limit is 10, so none is needed or possible now. No
  quota change was requested.
- Plans (read-only, not applied): defaults add/change/destroy nothing; the
  enabled review plan (placeholder digest and a placeholder parameter name) adds
  22 resources and changes the lifecycle configuration in place, with the SSM
  and `ListBucket` statements visible in the role policy and a precondition
  failure if the parameter name is missing.

## Tests

`tests/test_demo_auth.py` (106) covers: header parsing (14 defective forms); the
verifier (right, wrong, near-miss, constant-time structure, hash-only documents,
17 malformed documents); caching (once per period, rotation, failed refresh,
backoff, recovery, 8-way single load); the SSM request shape against the service
model; hosting config; every protected route with eight bad credentials (same
401 each); unauthenticated bad bodies; token absent from responses, records,
URLs, keys, and logs; public health and root; 503 for an unavailable verifier,
malformed value, SSM failure with recovery, and an unconfigured hosted app;
ownership with two principals (confirm, status, result all 404, owner unaffected,
no SQS, interleaved confirms send one message, a completed result stays
private, ownerless jobs invisible); local opt-in; the generator; dispatcher
separation; and no docs pages when hosted. `tests/test_api_terraform.py` (24)
adds static guards: `ListBucket` is bucket-level with a `StringLike` prefix
condition and appears once; exactly one SSM parameter; KMS only for an explicit
key; concurrency default and zero rejection; the removed escape hatch. Mutating
each guard fails a test. The existing hosted-upload and error-mapping suites run
under authentication; the missing-object (`upload_not_received`) and permission
failure (`503`) mappings are covered there.

Not run: anything against real SSM, S3, or API Gateway.

## Remaining deployment blockers

1. Create the SecureString parameter (generate tokens with the script), choose
   its name, and decide on a customer-managed KMS key (default is fine).
2. Confirm real S3 behavior for a missing source object under the new
   `ListBucket` statement.
3. Push the API image and record its digest; build the dispatcher zip.
4. Plan, review, apply, then smoke: 401 without a token, an end-to-end upload
   with a token, cross-token 404, dispatcher start.
5. The token travels in an HTTPS header; rotate by updating the parameter (live
   within 5 minutes) and never log request headers.
