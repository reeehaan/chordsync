# S6-T03 AWS adapters and runtime composition

This ticket adds testable AWS adapters without provisioning or contacting AWS.
The existing FastAPI analysis path remains unchanged. The cloud-ready modules
are composed separately until the queue/executor migration can replace the
legacy in-memory `AnalysisJobRepository` safely.

## Runtime configuration

`CHORDSYNC_RUNTIME_MODE` accepts `local` (the default) or `aws`.

Local mode composes:

- `SqliteCloudJobRepository` at `STORAGE_PATH/cloud_local/jobs.sqlite3`;
- `LocalArtifactStorage` at `STORAGE_PATH/cloud_local/artifacts`.

AWS mode requires `AWS_REGION`, `CHORDSYNC_S3_BUCKET`, and
`CHORDSYNC_DYNAMODB_JOB_TABLE`. It composes `DynamoDbCloudJobRepository` and
`S3ArtifactStorage`. Credentials are never configuration fields: boto3 uses its
normal credential provider chain. Composition creates SDK clients but performs
no bucket/table creation and no data request.

The remaining legacy integration points are the FastAPI router's
`AnalysisJobService`, `InMemoryAnalysisJobRepository`, local-path input storage,
and `InProcessAnalysisJobExecutor`. Replacing only part of that chain would make
result retrieval and execution unsafe, so it is deferred to the queue/executor
ticket.

## S3 adapter and security assumptions

`S3ArtifactStorage` implements byte put/read/existence/delete against the
existing `ArtifactStorage` interface. It records SHA-256 as private object
metadata, preserves content type and size in the returned metadata, and treats
ETag only as transport metadata. Writes request SSE-S3 (`AES256`) by default;
deployment may rely additionally on bucket default encryption.

The future bucket must have:

- Block Public Access enabled and bucket-owner-enforced object ownership;
- no ACL-based sharing (the adapter sends no ACL field);
- default encryption, plus HTTPS-only bucket policy;
- least-privilege, separate API/worker IAM roles;
- private source, playback, and result prefixes;
- short-lived presigned access only after API authorization.

`ObjectAccessSigner` is the separate future API-level interface for upload and
download signing. It accepts a validated artifact key, operation, expiry, and
optional content type. It is deliberately not implemented or wired to Flutter
in this ticket.

## DynamoDB adapter and capacity

One item stores the scalar `CloudJobRecord` attributes under
`PK = JOB#{job_id}`. Create uses `attribute_not_exists(PK)`. Save replaces the
item only when both the stored optimistic version and expected state match.
Conditional failures become `JobWriteConflictError`; provider errors do not
expose response bodies or deployment identifiers.

Start with DynamoDB On-Demand for the approximately $20/month project budget.
Do not tune provisioned capacity and do not add a GSI until a real query pattern
requires one. A TTL is only a future candidate for transient job metadata; it
must not govern retained saved-song records.

## Retention and lifecycle mapping

- `jobs/*/source/*`: target expiry about one day after a successful workflow;
- intermediates: remain worker-local where possible and are not persisted;
- playback: retained while the saved song exists;
- timeline: retained while the saved song exists.

S3 lifecycle cannot inspect application job state. A prefix-only one-day rule
could delete a slow or abandoned active upload based solely on object age. Tag
source objects after successful publication (for example, an expiry-intent tag)
and scope lifecycle to that tag, or use application cleanup. No lifecycle rules
or tags are created by this ticket.

## Error model

Provider failures are reduced to `temporary_unavailable`, `not_found`,
`conditional_conflict` (the repository's existing write-conflict exception),
`configuration_error`, or `unexpected_provider_error`. Messages avoid bucket
names, table names, account IDs, credentials, and AWS response bodies.
