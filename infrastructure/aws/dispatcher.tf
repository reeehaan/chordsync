# Worker dispatcher Lambda (S7-T04): starts one Fargate worker when the analysis
# queue has visible work and no worker is active. DESIGN ONLY: every resource is
# gated by local.dispatcher_on (dispatcher_enabled or hosted_api_enabled, both
# default false), so a default plan creates nothing; nothing here starts compute
# at apply time. The function reads SQS queue attributes only; it
# can never receive, delete, or hide a message.
# See docs/cloud/s7-t04-worker-dispatcher.md.

variable "dispatcher_enabled" {
  description = "Create the worker dispatcher Lambda and its role on its own. hosted_api_enabled also creates it."
  type        = bool
  default     = false
}

variable "dispatcher_schedule_enabled" {
  description = "Create the periodic reconcile schedule whenever the dispatcher exists."
  type        = bool
  default     = true
}

variable "dispatcher_schedule_rate" {
  description = "How often the scheduled reconcile runs."
  type        = string
  default     = "rate(5 minutes)"
}

variable "dispatcher_package_path" {
  description = "Zip built by scripts/build_dispatcher_package.py (Python code only)."
  type        = string
  default     = "../../build/dispatcher/chordsync-dispatcher.zip"
}

locals {
  # The dispatcher exists when asked for, or whenever the hosted API does (the
  # API invokes it). The schedule follows the dispatcher.
  dispatcher_on          = var.dispatcher_enabled || var.hosted_api_enabled
  dispatcher_schedule_on = local.dispatcher_on && var.dispatcher_schedule_enabled
  dispatcher_name        = "${local.name_prefix}-worker-dispatcher"
  dispatcher_lock_key    = "LOCK#worker-dispatch"
  worker_family_arn      = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${aws_ecs_task_definition.worker.family}"
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "dispatcher_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dispatcher" {
  count              = local.dispatcher_on ? 1 : 0
  name               = "${local.dispatcher_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.dispatcher_trust.json
}

resource "aws_cloudwatch_log_group" "dispatcher" {
  count             = local.dispatcher_on ? 1 : 0
  name              = "/aws/lambda/${local.dispatcher_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "dispatcher" {
  statement {
    sid       = "ReadQueueDepth"
    actions   = ["sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.analysis.arn]
  }

  statement {
    sid       = "ListWorkerTasks"
    actions   = ["ecs:ListTasks"]
    resources = ["*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.analysis.arn]
    }
  }

  statement {
    sid       = "DescribeWorkerTasks"
    actions   = ["ecs:DescribeTasks"]
    resources = ["arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task/${aws_ecs_cluster.analysis.name}/*"]
  }

  statement {
    sid       = "StartWorkerTask"
    actions   = ["ecs:RunTask"]
    resources = ["${local.worker_family_arn}:*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.analysis.arn]
    }
  }

  statement {
    sid     = "PassWorkerRolesToEcsOnly"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.worker.arn,
      aws_iam_role.ecs_execution.arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "HoldDispatchLease"
    actions   = ["dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.jobs.arn]

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "dynamodb:LeadingKeys"
      values   = [local.dispatcher_lock_key]
    }
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.dispatcher_name}:*"]
  }
}

resource "aws_iam_role_policy" "dispatcher" {
  count  = local.dispatcher_on ? 1 : 0
  name   = "worker-dispatcher"
  role   = aws_iam_role.dispatcher[0].id
  policy = data.aws_iam_policy_document.dispatcher.json
}

resource "aws_lambda_function" "dispatcher" {
  count         = local.dispatcher_on ? 1 : 0
  function_name = local.dispatcher_name
  role          = aws_iam_role.dispatcher[0].arn
  runtime       = "python3.13"
  architectures = ["arm64"]
  handler       = "backend.dispatcher.handler.lambda_handler"
  filename      = var.dispatcher_package_path
  # sha256 of the zip, so a rebuilt package is always redeployed.
  source_code_hash = filebase64sha256(var.dispatcher_package_path)
  memory_size      = 128
  timeout          = 30

  environment {
    variables = {
      CHORDSYNC_ECS_CLUSTER              = aws_ecs_cluster.analysis.name
      CHORDSYNC_WORKER_TASK_DEFINITION   = aws_ecs_task_definition.worker.family
      CHORDSYNC_WORKER_SUBNET_IDS        = join(",", data.aws_subnets.worker_public.ids)
      CHORDSYNC_WORKER_SECURITY_GROUP_ID = aws_security_group.analysis_worker.id
      CHORDSYNC_SQS_ANALYSIS_QUEUE_URL   = aws_sqs_queue.analysis.url
      CHORDSYNC_DYNAMODB_JOB_TABLE       = aws_dynamodb_table.jobs.name
      CHORDSYNC_MAX_WORKER_TASKS         = "1"
      CHORDSYNC_DISPATCH_LEASE_SECONDS   = "60"
    }
  }

  depends_on = [aws_cloudwatch_log_group.dispatcher, aws_iam_role_policy.dispatcher]
}

# Periodic reconcile: restarts compute for retries and missed notifications.
resource "aws_cloudwatch_event_rule" "dispatcher_schedule" {
  count               = local.dispatcher_schedule_on ? 1 : 0
  name                = "${local.dispatcher_name}-schedule"
  schedule_expression = var.dispatcher_schedule_rate
}

resource "aws_cloudwatch_event_target" "dispatcher_schedule" {
  count = local.dispatcher_schedule_on ? 1 : 0
  rule  = aws_cloudwatch_event_rule.dispatcher_schedule[0].name
  arn   = aws_lambda_function.dispatcher[0].arn
  input = jsonencode({ reason = "scheduled_reconcile" })
}

resource "aws_lambda_permission" "dispatcher_schedule" {
  count         = local.dispatcher_schedule_on ? 1 : 0
  statement_id  = "AllowScheduledReconcile"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dispatcher_schedule[0].arn
}

# The hosted API's role (api.tf) holds lambda:InvokeFunction on this function only.
output "dispatcher_function_name" {
  description = "Name the API uses for the asynchronous dispatcher nudge (empty while disabled)."
  value       = local.dispatcher_on ? aws_lambda_function.dispatcher[0].function_name : ""
}

output "dispatcher_function_arn" {
  description = "Dispatcher Lambda ARN (empty while disabled)."
  value       = local.dispatcher_on ? aws_lambda_function.dispatcher[0].arn : ""
}

output "dispatcher_log_group_name" {
  description = "Dispatcher Lambda log group (empty while disabled)."
  value       = local.dispatcher_on ? aws_cloudwatch_log_group.dispatcher[0].name : ""
}
