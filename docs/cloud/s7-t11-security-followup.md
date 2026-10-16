# S7-T11 Security follow-up (in progress)

Order of work, chosen to avoid lockout: (1) take the public runtime down, (2) register
MFA for IAM user `rehan` (manual), (3) enable the admin-group MFA guard, (4) require MFA
for `ChordSyncTerraformRole`, (5) activate alert delivery, (6) clean up obsolete
credentials and IAM resources. This file records progress; it is updated as each phase
completes.

## Phase 1: hosted runtime disabled (done, 2026-10-16)

`terraform apply -var hosted_api_enabled=false -var dispatcher_enabled=false`, applied from
a saved plan after fmt, validate, and review: **0 added, 1 changed, 28 destroyed**; a
follow-up plan is 0/0/0.

Destroyed (all hosted-runtime resources; every one is recreated by re-enabling):

- API Gateway: the HTTP API `1vdojhtkg8`, its integration, six routes, and `$default` stage.
- Lambda: the API function and the dispatcher function, their two IAM roles and role
  policies, and the two Lambda permissions (API Gateway invoke, schedule invoke).
- The 5-minute schedule rule and its target.
- Log groups: API, API access, and dispatcher (7-day logs from the S7-T08/T09 runs; the
  evidence is recorded in the S7-T08/T09 documents).
- Four alarms and two log metric filters that exist only while the hosted functions do:
  API-errors, dispatcher-errors, dispatcher-failures, worker-start-burst; the
  `dispatcher-failures` and `worker-starts` filters. **This removes part of the S7-T10
  monitoring while the runtime is off**, because those alarms read the destroyed
  functions and log groups. They return on re-enable.

Changed: `aws_s3_bucket_lifecycle_configuration.artifacts` loses the
`expire-abandoned-source-uploads` rule (it is gated by `hosted_api_enabled`). While the API
is off nothing creates presigned uploads. The one tagged source object left from the
S7-T08 smoke job will not expire until the rule returns; on re-enable the rule applies to
existing tagged objects older than two days.

Retained (not in the plan): the S3 artifact bucket and its 6 job objects, the DynamoDB
table (3 items), both SQS queues, both ECR repositories (API images `api-2ed4afa-s7` and
`api-s7t07-runtime1`), the SSM parameter `/chordsync/demo/auth/token-verifiers`, the
worker task definition and cluster, the SNS topic, the budget, CloudTrail, the password
policy, the SQS queue-depth and DLQ alarms, and the failed-worker EventBridge rule.

Verified afterwards: the old endpoint no longer connects (no HTTP response); API
Gateway APIs 0; Lambda functions 0; ECS tasks 0 and services 0; queue 0/0; DLQ 0; no
Fargate task started.

To bring it back (after the auth work is finished):
`terraform apply -var hosted_api_enabled=true -var api_image_digest=sha256:bc9b30b6d5d87006bdac420e5614c747ac91e24598f11addb53f6efe073e82ca -var demo_token_parameter_name=/chordsync/demo/auth/token-verifiers -var api_reserved_concurrency=-1 -var dispatcher_enabled=true -var dispatcher_schedule_enabled=true`
(from a reviewed saved plan). The dispatcher zip must exist at
`build/dispatcher/chordsync-dispatcher.zip` (hash `f382488f…d48a`).

## Phase 2: MFA registered for `rehan` (done, 2026-10-16)

Virtual device `arn:aws:iam::396765697713:mfa/iam-rehan-authenticator`, enabled
2026-10-16 12:24 UTC, confirmed read-only (the root account's own MFA is untouched).

## Phase 3: admin-group MFA guard (applied, 2026-10-16)

`terraform apply -var enforce_admin_mfa=true` (hosted runtime still off) from a saved
plan: **2 added, 0 changed, 0 destroyed**: the IAM policy `chordsync-require-mfa` and its
attachment to group `admin`. Drift plan afterwards: 0/0/0.

Rendered policy, as reviewed before applying:

- Allow: `iam:ChangePassword`, `Create/Delete/Enable/Resync/List` virtual MFA device
  actions, `iam:GetUser`, `GetAccountSummary`, `GetAccountPasswordPolicy`,
  `ListAccountAliases`, `ListUsers` (set up or recover an MFA device).
- Deny `NotAction` of those plus `sts:AssumeRole`, `sts:GetCallerIdentity`,
  `sts:GetSessionToken`, only when `BoolIfExists aws:MultiFactorAuthPresent = false`.
  So a session with MFA is unaffected, and a session without it (including the stored
  access key used directly) can only set up MFA, check its identity, or assume a role.

Checks after the apply: the `chordsync-terraform` role path still works
(`sts get-caller-identity`, IAM read, Terraform plan). The base access key used directly
(no MFA) now gets AccessDenied for S3, EC2 and IAM listing calls, while STS identity and
MFA lookup work. The first retest right after applying still succeeded; IAM changes take
about 20 seconds to propagate, so the denial was confirmed on the retest.

Safety net: the guard applies to the user `rehan` through its group, not to role
sessions, so the role path can still remove the guard if needed
(`terraform apply -var enforce_admin_mfa=false`). A console session opened before MFA
was registered loses its admin rights immediately; signing out and back in with an MFA
code restores them.

**The flag is not stored anywhere.** Every future plan must include
`-var enforce_admin_mfa=true`, or Terraform will propose removing the guard. Changing the
variable's default to `true` (or adding a `terraform.tfvars`) would make this permanent.

Still to verify by you in the console (cannot be done from the CLI): sign out, sign in
again as `rehan` with an MFA code, and confirm that an ordinary admin page (for example
IAM → Roles) loads. Phase 4 (MFA on `ChordSyncTerraformRole`, `mfa_serial` in the CLI
profile) has not been started.

## Phase 4: MFA required for `ChordSyncTerraformRole` (done, 2026-10-16)

Order followed: MFA device registered, admin-group guard applied and tested, then:

1. Added `mfa_serial = arn:aws:iam::396765697713:mfa/iam-rehan-authenticator` to the
   `chordsync-terraform` profile in `~/.aws/config` (original saved as
   `~/.aws/config.bak-s7t11`).
2. Obtained an MFA-backed role session (the user entered the code in their own terminal;
   the CLI cached the session). `sts get-caller-identity` returned the role ARN, a
   harmless read-only call and a Terraform plan (0/0/0) worked.
3. Replaced the role's trust policy (it is not Terraform-managed) with the same principal
   (`user/rehan`) plus `Condition: Bool aws:MultiFactorAuthPresent = "true"`. The previous
   document was saved for rollback.
4. Tested: the base access key without MFA calling `sts:AssumeRole` on the role is
   **AccessDenied**. The cached session was cleared and the user logged in again with a
   fresh code under the new trust: it worked.

Effect: the stored access key alone can no longer reach admin, either directly (the group
guard) or through the role (the trust condition). A session needs a current authenticator
code, valid for about an hour.

**Terraform and MFA.** Terraform's AWS provider cannot prompt for a code, so with
`mfa_serial` set the profile fails ("assume role with MFA enabled, but
AssumeRoleTokenProvider session option not set"). Run Terraform with credentials exported
from the cached CLI session instead (nothing is written to disk):

```
aws sts get-caller-identity --profile chordsync-terraform   # enter the code once per hour
unset AWS_PROFILE
eval "$(aws configure export-credentials --profile chordsync-terraform --format env)"
terraform plan -var enforce_admin_mfa=true ...
```

**Rollback:** an MFA-signed console session (admin through the group) can edit the role's
trust policy back to the saved original; `terraform apply -var enforce_admin_mfa=false`
(through an MFA role session) removes the group guard.

CloudTrail Event history lags a few minutes, so the MFA console sign-in and the new
`AssumeRole` events were not yet visible when this was written.

Not done: the active access key was not rotated or removed (still used by the CLI profile);
`alert_email` is still unset; the inactive key, empty `new-admin` group, and unused roles
remain; `enforce_admin_mfa` still defaults to `false` (every plan needs
`-var enforce_admin_mfa=true`).

## Phase 5: alert delivery (applied, 2026-10-16)

The user supplied the address explicitly; it is not written into the repository. It lives in
a private file outside the repo, `~/.chordsync-terraform/local.tfvars` (directory 700, file
600), together with `enforce_admin_mfa = true`. Pass it to every plan and apply:

```
terraform plan -var-file=$HOME/.chordsync-terraform/local.tfvars ...
```

Without it Terraform would propose removing the email subscription, the budget alerts, and
the MFA guard. Applied from a saved plan: **1 added, 1 changed, 0 destroyed**: the SNS email
subscription, and the budget gained its notifications (actual spend at 25%, 50%, 80%, 100%
of USD 20, plus a forecasted 100%). Drift afterwards: 0/0/0.

The budget emails go straight to the address. The SNS subscription starts as
`PendingConfirmation`; the alarm and failed-worker emails start only after the
"AWS Notification - Subscription Confirmation" email's link is clicked.

## Phase 6: cleanup (done, 2026-10-16)

The SNS subscription was confirmed first. Removed, each after checking it was unused:

- The **inactive** access key `AKIAVYYI…5HSO` of user `rehan` (created 2025-10-10,
  last used 2026-05-24). The active key `…4OB4FVIZ` was not touched.
- The empty group `new-admin` (it held AdministratorAccess and had no members). The
  `admin` group is unchanged.
- The unused Terraform-managed role `chordsync-student-demo-api-task` and its policy
  (never used, broader than needed: `Scan`, `UpdateItem`, source `PutObject`), plus the
  `api_role_arn` output that pointed at it. Terraform: **0 added, 0 changed, 2 destroyed**;
  drift afterwards 0/0/0. This is a source change in `iam.tf` and `outputs.tf`
  (uncommitted).

**Deliberately kept.** The legacy roles (`challenge1-role-*`, `my-lambda-function-role-*`,
`sam-first-project-*`, `todo-crud-app-*`) are not obsolete: they run 13 Lambda functions
and four CloudFormation stacks (`sam-first-project`, `todo-crud-app`, `challenge1`,
`post-and-pray-backend`, plus the SAM CLI managed stack) in `ap-south-1`, with live API
Gateways and the `todos` and `PostAndPray` DynamoDB tables. They belong to other projects, and deleting
them would break those apps. `DemoRoleForEC2` is unused (no instances, never used) but is
outside ChordSync, so it was left for the owner to decide.

Also not changed: the worker role's unused `dynamodb:UpdateItem` (removing it would need a
real analysis to verify).
