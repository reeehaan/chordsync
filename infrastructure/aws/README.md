# ChordSync private AWS foundation

This directory defines the first private, single-region ChordSync AWS stack in
Terraform. It is infrastructure definition only: no AWS resource has been
created, and no credentials belong in this directory.

Terraform was selected because the repository has no existing IaC convention,
the stack is small, and reviewable HCL adds less project tooling than CDK. Use
one IaC system only.

## Frozen constraints

- Region: `ap-southeast-1` (Singapore), configurable but single-region.
- Target budget: approximately USD 20/month.
- Upload: WAV/MP3/M4A, at most 25 MB and six minutes.
- Private/student demo: no authentication yet.
- MUSIC_ONLY remains disabled.
- No Spotify synchronized playback.
- The exact analyzed source is retained as playback; worker intermediates are
  local and disposable.

```text
Flutter
   ↓
FastAPI
   ↓
DynamoDB job state
   ↓
private S3 source
   ↓
SQS analysis queue
   ↓
ECS worker task
   ↓
private S3 playback + timeline
   ↓
DynamoDB completed state
```

## Defined resources and deliberate omissions

The stack defines one private S3 bucket, one On-Demand DynamoDB table, standard
analysis and dead-letter queues, private API/worker ECR repositories, distinct
API/worker/execution IAM roles, an ECS cluster, a Fargate ARM64 worker task
definition pinned to the approved image digest (`worker_image_digest`), a
seven-day worker log group, two native SQS alarms, and an optional USD 20 AWS
Budget. See `docs/cloud/s6-t12-worker-deployment.md` for the controlled
runtime-test configuration.

It deliberately defines no ECS service, EC2 Auto Scaling Group, GPU instance,
VPC, NAT Gateway, load balancer, public endpoint, Route 53 record, or API task.
Therefore the worker foundation has zero running capacity; compute cost is
incurred only while an explicitly started one-shot task runs.

The first API hosting recommendation is a cheap externally hosted or
serverless/lightweight container endpoint that can assume the scoped API role
through an appropriate deployment mechanism. An always-running ECS/Fargate API
is viable technically, but Fargate plus an Application Load Balancer introduces
fixed runtime cost that may consume or exceed the project budget. If ECS API
hosting is selected later, add its task definition, service, ingress, TLS, and
logs only after a current Singapore-region estimate.

## Storage and retention

The bucket has all four Block Public Access controls, bucket-owner-enforced
ownership (ACLs disabled), SSE-S3 default encryption, an HTTPS-only deny policy,
and no website configuration. Versioning is suspended for the student demo to
avoid retaining replaced audio copies. Enable it only with a lifecycle/cost
plan.

Logical private prefixes remain:

```text
jobs/{job_id}/source/
jobs/{job_id}/playback/
jobs/{job_id}/results/
jobs/{job_id}/debug/
```

Source expiry is tag-gated: only an object tagged
`chordsync-expire-source=true` expires after approximately one day. Upload age
alone never deletes an active analysis. The application does not apply this tag
yet; add `PutObjectTagging` to exactly one cleanup actor when that workflow is
implemented. Debug objects tagged `chordsync-artifact-role=debug` expire after
seven days. Playback and timeline objects have no automatic expiry. A future
saved-song deletion operation must delete both explicitly. Incomplete multipart
uploads are aborted after one day.

## State, queues, and encryption

DynamoDB uses `PAY_PER_REQUEST`, `PK` string keys (`JOB#{job_id}` in the
application), AWS-owned default encryption, no GSI, no TTL, and no provisioned
capacity. Point-in-time recovery and deletion protection are disabled for this
re-creatable student environment to minimize cost and friction; reconsider both
before storing valuable user libraries.

Both SQS queues are standard and use SQS-managed encryption, avoiding a
customer-managed KMS key's recurring/request cost. The main queue retains
messages for one day and redrives after three receives. The DLQ retains messages
for fourteen days. The temporary visibility timeout is 20 minutes, based on the
~4m47s projected maximum-song Mac runtime plus substantial margin. Benchmark on
the selected Linux/AWS worker before production and use the application's
visibility-extension interface for a heartbeat.

## Networking decision

Terraform defines only the egress-only `chordsync-analysis-worker` security
group and reads the default VPC's public subnets (`network.tf`); no VPC,
subnet, NAT, or endpoint is created. For the private demo, the selected direction is a
one-shot Fargate worker task in a public subnet with a public IP, a security
group with no inbound rules and HTTPS-only egress, and IAM-scoped access. The
task exposes no inbound ports; models come from the private S3 model prefix,
not public downloads. A private subnet plus NAT Gateway is stronger isolation
but the NAT hourly/data charges can independently threaten USD 20/month. The
interface endpoints a private Fargate task would need (ECR API, ECR DKR, Logs,
SQS) also carry hourly cost that exceeds the budget. Do not add NAT by default.

## Model cache recommendation

The approved worker image contains no model weights or BTC assets, and its
digest is bound to a security exception, so models are not baked into it.
Model assets are staged under a private, SHA-256-manifested S3 prefix and
copied into the task's ephemeral cache by a bootstrap step before analysis.
`HF_HUB_OFFLINE=1` prevents uncontrolled Hugging Face downloads. The manifest
format, key layout, provenance, and bootstrap behaviour are in
`docs/cloud/s6-t13-model-bootstrap.md`.

EFS and EBS caches add fixed cost and complicate scale-to-zero; framework
downloads at task start are non-deterministic, so neither is the first choice.

## Monitoring and budget protection

Worker logs expire after seven days. Native AWS/SQS metrics drive queue-depth
and DLQ-nonempty alarms; Container Insights and custom metrics are disabled.
The alarm definitions have no notification topic yet—connect an SNS destination
during controlled provisioning.

Set `alert_email` to deliver the USD 20 monthly AWS Budget alerts (the budget itself always exists; see `docs/cloud/s7-t10-account-hardening.md`): actual-spend
emails at 25%, 50%, 80%, and 100%, plus a forecasted-100% email. AWS Budgets alerts; it does **not** hard-stop
services or guarantee a spending ceiling.

Cost classification:

- Near-zero/usage-based: S3 at demo volume, On-Demand DynamoDB, SQS, ECR storage,
  short-retention logs, native alarms, and AWS Budget.
- Small fixed/retained cost: ECR images, CloudWatch logs, and any later EBS cache.
- Potentially over USD 20 independently: NAT Gateway, ALB, always-on Fargate,
  always-on EC2/GPU, large EBS volumes, excessive logs/custom metrics, model
  downloads, and internet data transfer.

Always review current `ap-southeast-1` pricing before provisioning; this document
does not claim a precise monthly total.

## Local validation only

```sh
cd infrastructure/aws
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

Initialization downloads provider schemas but does not create resources. Never
run `terraform apply` or any deploy command as part of this ticket. Before the
first controlled provisioning, configure a reviewed remote state backend and
run `terraform plan` with the intended AWS identity.

Application configuration comes from the non-secret outputs:

- `AWS_REGION`
- `CHORDSYNC_S3_BUCKET`
- `CHORDSYNC_DYNAMODB_JOB_TABLE`
- `CHORDSYNC_SQS_ANALYSIS_QUEUE_URL`

Role/task ARNs and the ECR URL are deployment metadata, not credentials.
