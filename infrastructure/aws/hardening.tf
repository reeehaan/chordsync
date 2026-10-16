# Account hardening (S7-T10): alert channel, cost budget, operational alarms,
# CloudTrail management-event audit, a password policy, and an OPTIONAL MFA
# guard (off by default because enabling it before the IAM user has an MFA device
# would lock that user out of console administration).
# Nothing here changes application infrastructure.
# See docs/cloud/s7-t10-account-hardening.md.

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD. Expected spend is a few dollars; this is the ceiling the alerts are measured against."
  type        = number
  default     = 20
}

variable "cloudtrail_enabled" {
  description = "Create the management-event CloudTrail trail and its private log bucket."
  type        = bool
  default     = true
}

variable "cloudtrail_log_retention_days" {
  description = "Days before CloudTrail log files are expired from S3."
  type        = number
  default     = 90
}

variable "enforce_admin_mfa" {
  description = "Attach a deny-unless-MFA policy to the existing IAM group named by admin_group_name. Register an MFA device for every member FIRST, or console administration is blocked until they do."
  type        = bool
  default     = false
}

variable "admin_group_name" {
  description = "Existing IAM group whose members get the MFA guard when enforce_admin_mfa is true."
  type        = string
  default     = "admin"
}

variable "worker_starts_per_hour_alarm" {
  description = "Alarm when the dispatcher starts at least this many workers in one hour (a loop detector; a demo normally starts a handful)."
  type        = number
  default     = 10
}

# --- alert channel -------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

data "aws_iam_policy_document" "alerts_topic" {
  statement {
    sid       = "AlarmsAndEventsMayPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com", "events.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts_topic.json
}

# Created only when an address is supplied; the recipient must confirm it.
resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- cost budget -----------------------------------------------------------------

locals {
  # Percent of the budget; with the default 20 USD these are 5, 10, 16 and 20 dollars.
  budget_actual_alerts = [25, 50, 80, 100]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Alerts exist only once an address is supplied (the budget itself is always
  # tracked and visible in the console).
  dynamic "notification" {
    for_each = var.alert_email == "" ? [] : local.budget_actual_alerts

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }

  dynamic "notification" {
    for_each = var.alert_email == "" ? [] : [100]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [var.alert_email]
    }
  }
}

# --- operational alarms (hosted stack only) ---------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_lambda_errors" {
  count               = local.api_on ? 1 : 0
  alarm_name          = "${local.name_prefix}-api-lambda-errors"
  alarm_description   = "The API Lambda raised an unhandled error or timed out."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.api[0].function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "dispatcher_lambda_errors" {
  count               = local.dispatcher_on ? 1 : 0
  alarm_name          = "${local.name_prefix}-dispatcher-lambda-errors"
  alarm_description   = "The worker dispatcher failed (configuration or runtime error)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.dispatcher[0].function_name
  }
}

# The dispatcher reports run_task_failed / dependency_unavailable as a normal
# return, so the Lambda Errors metric never sees them; count them from the log.
resource "aws_cloudwatch_log_metric_filter" "dispatcher_failures" {
  count          = local.dispatcher_on ? 1 : 0
  name           = "dispatcher-failures"
  log_group_name = aws_cloudwatch_log_group.dispatcher[0].name
  pattern        = "?\"run_task_failed\" ?\"dependency_unavailable\""

  metric_transformation {
    name          = "DispatcherFailures"
    namespace     = "ChordSync/Dispatcher"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "dispatcher_failures" {
  count               = local.dispatcher_on ? 1 : 0
  alarm_name          = "${local.name_prefix}-dispatcher-failures"
  alarm_description   = "The dispatcher could not start a worker or reach a dependency (RunTask failed, capacity, throttling, SSM/SQS/ECS errors)."
  namespace           = "ChordSync/Dispatcher"
  metric_name         = "DispatcherFailures"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Spend-loop detector: one worker per job is normal; a burst of starts is not.
resource "aws_cloudwatch_log_metric_filter" "worker_starts" {
  count          = local.dispatcher_on ? 1 : 0
  name           = "worker-starts"
  log_group_name = aws_cloudwatch_log_group.dispatcher[0].name
  pattern        = "\"worker_started\""

  metric_transformation {
    name          = "WorkerStarts"
    namespace     = "ChordSync/Dispatcher"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_start_burst" {
  count               = local.dispatcher_on ? 1 : 0
  alarm_name          = "${local.name_prefix}-worker-start-burst"
  alarm_description   = "Many Fargate workers were started within an hour; check for a retry or scheduling loop."
  namespace           = "ChordSync/Dispatcher"
  metric_name         = "WorkerStarts"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = var.worker_starts_per_hour_alarm
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# A worker task that failed to start or exited non-zero.
resource "aws_cloudwatch_event_rule" "worker_task_failed" {
  name        = "${local.name_prefix}-worker-task-failed"
  description = "A ChordSync worker task stopped with an error."

  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.analysis.arn]
      lastStatus = ["STOPPED"]
      "$or" = [
        { containers = { exitCode = [{ "anything-but" = 0 }] } },
        { stopCode = ["TaskFailedToStart"] },
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "worker_task_failed" {
  rule = aws_cloudwatch_event_rule.worker_task_failed.name
  arn  = aws_sns_topic.alerts.arn
}

# --- CloudTrail: management events only --------------------------------------------

resource "aws_s3_bucket" "cloudtrail" {
  count         = var.cloudtrail_enabled ? 1 : 0
  bucket_prefix = "${local.name_prefix}-cloudtrail-"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  count                   = var.cloudtrail_enabled ? 1 : 0
  bucket                  = aws_s3_bucket.cloudtrail[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "cloudtrail" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail[0].id

  rule {
    id     = "expire-trail-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = var.cloudtrail_log_retention_days
    }
  }
}

locals {
  trail_name = "${var.project_name}-management-events"
  trail_arn  = "arn:aws:cloudtrail:${var.aws_region}:${data.aws_caller_identity.current.account_id}:trail/${local.trail_name}"
}

data "aws_iam_policy_document" "cloudtrail_bucket" {
  count = var.cloudtrail_enabled ? 1 : 0

  statement {
    sid       = "CloudTrailAclCheck"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail[0].arn]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid       = "CloudTrailWrite"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cloudtrail[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.cloudtrail[0].arn,
      "${aws_s3_bucket.cloudtrail[0].arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail[0].id
  policy = data.aws_iam_policy_document.cloudtrail_bucket[0].json

  depends_on = [aws_s3_bucket_public_access_block.cloudtrail]
}

# One multi-region trail for management events. No data events (S3 objects,
# Lambda invokes) and no CloudWatch Logs delivery, which keeps the cost at the
# S3 storage of a few small files: the first management-event trail is free.
resource "aws_cloudtrail" "management" {
  count                         = var.cloudtrail_enabled ? 1 : 0
  name                          = local.trail_name
  s3_bucket_name                = aws_s3_bucket.cloudtrail[0].id
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.cloudtrail]
}

# --- IAM account basics -------------------------------------------------------------

# Applies to new or changed passwords only; passwords never expire, so no
# existing user is forced out.
resource "aws_iam_account_password_policy" "baseline" {
  minimum_password_length        = 14
  require_lowercase_characters   = true
  require_uppercase_characters   = true
  require_numbers                = true
  require_symbols                = true
  allow_users_to_change_password = true
  password_reuse_prevention      = 5
  max_password_age               = 0
  hard_expiry                    = false
}

# OPTIONAL: deny almost everything for a signed-in user without MFA, while
# leaving the actions needed to register a device. sts:AssumeRole stays allowed
# so the Terraform role workflow keeps working. Off by default.
data "aws_iam_policy_document" "require_mfa" {
  statement {
    sid    = "AllowManageOwnMfaAndPassword"
    effect = "Allow"
    actions = [
      "iam:ChangePassword",
      "iam:CreateVirtualMFADevice",
      "iam:DeleteVirtualMFADevice",
      "iam:EnableMFADevice",
      "iam:GetAccountPasswordPolicy",
      "iam:GetAccountSummary",
      "iam:GetUser",
      "iam:ListAccountAliases",
      "iam:ListMFADevices",
      "iam:ListUsers",
      "iam:ListVirtualMFADevices",
      "iam:ResyncMFADevice",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DenyEverythingElseWithoutMfa"
    effect = "Deny"
    not_actions = [
      "iam:ChangePassword",
      "iam:CreateVirtualMFADevice",
      "iam:DeleteVirtualMFADevice",
      "iam:EnableMFADevice",
      "iam:GetAccountPasswordPolicy",
      "iam:GetAccountSummary",
      "iam:GetUser",
      "iam:ListAccountAliases",
      "iam:ListMFADevices",
      "iam:ListUsers",
      "iam:ListVirtualMFADevices",
      "iam:ResyncMFADevice",
      "sts:AssumeRole",
      "sts:GetCallerIdentity",
      "sts:GetSessionToken",
    ]
    resources = ["*"]

    condition {
      test     = "BoolIfExists"
      variable = "aws:MultiFactorAuthPresent"
      values   = ["false"]
    }
  }
}

resource "aws_iam_policy" "require_mfa" {
  count       = var.enforce_admin_mfa ? 1 : 0
  name        = "${var.project_name}-require-mfa"
  description = "Blocks most actions for the admin group until the user signs in with MFA."
  policy      = data.aws_iam_policy_document.require_mfa.json
}

resource "aws_iam_group_policy_attachment" "require_mfa" {
  count      = var.enforce_admin_mfa ? 1 : 0
  group      = var.admin_group_name
  policy_arn = aws_iam_policy.require_mfa[0].arn
}

# --- outputs -------------------------------------------------------------------------

output "alerts_topic_arn" {
  description = "SNS topic for alarms and failed-worker events."
  value       = aws_sns_topic.alerts.arn
}

output "cloudtrail_bucket" {
  description = "Private bucket holding management-event logs (empty if CloudTrail is disabled)."
  value       = var.cloudtrail_enabled ? aws_s3_bucket.cloudtrail[0].id : ""
}
