# Hosted API (S7-T05): API Gateway HTTP API -> Lambda container (FastAPI behind
# AWS Lambda Web Adapter), plus its role, logs, throttling, and the permission
# to nudge the worker dispatcher. PLAN-READY ONLY: everything below is gated by
# var.hosted_api_enabled (default false), so a default plan creates nothing.
#
# AUTH: the API authenticates every /analysis call with a demo bearer token
# whose SHA-256 verifier lives in one SSM parameter (created out of band, never
# by Terraform, so the verifier stays out of state). The plan fails unless
# demo_token_parameter_name is set. See docs/cloud/s7-t06-demo-auth.md.
#
# No NAT, no load balancer, no always-on ECS service, no function URL.
# See docs/cloud/s7-t05-api-infrastructure.md.

variable "hosted_api_enabled" {
  description = "Create the hosted API (API Gateway, API Lambda, role, logs) and the dispatcher. Keep false until the auth ticket is done."
  type        = bool
  default     = false
}

variable "demo_token_parameter_name" {
  description = "Name of the SSM parameter (SecureString) holding the demo-token verifier document. Required when hosted_api_enabled. Terraform never creates or reads it."
  type        = string
  default     = ""

  validation {
    condition     = var.demo_token_parameter_name == "" || can(regex("^/?[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$", var.demo_token_parameter_name))
    error_message = "demo_token_parameter_name must be a valid SSM parameter name such as /chordsync/demo/auth/token-verifiers."
  }
}

variable "demo_token_kms_key_arn" {
  description = "Only if the parameter is encrypted with a customer-managed KMS key: its ARN, so the API role can decrypt it. Leave empty for the default aws/ssm key, which needs no extra permission."
  type        = string
  default     = ""
}

variable "api_image_digest" {
  description = "Immutable digest of the pushed API image, for example sha256:<64 hex>. Required when hosted_api_enabled. Tags are never used."
  type        = string
  default     = ""
}

variable "api_reserved_concurrency" {
  description = "Reserved concurrent executions for the API Lambda. -1 means none (the default): this account's limit is 10 and AWS requires 10 unreserved, so nothing can be reserved until the quota is raised. Positive values are for after that. 0 is rejected because it blocks every call."
  type        = number
  default     = -1

  validation {
    condition     = var.api_reserved_concurrency == -1 || var.api_reserved_concurrency >= 1
    error_message = "api_reserved_concurrency must be -1 (no reservation) or a positive number; 0 would throttle every request."
  }
}

variable "api_throttle_rate_limit" {
  description = "Steady requests per second for the whole API stage."
  type        = number
  default     = 2
}

variable "api_throttle_burst_limit" {
  description = "Burst requests for the whole API stage."
  type        = number
  default     = 5
}

variable "api_write_throttle_rate_limit" {
  description = "Steady requests per second for create-job, confirm-upload and cancel."
  type        = number
  default     = 1
}

variable "api_write_throttle_burst_limit" {
  description = "Burst requests for create-job, confirm-upload and cancel."
  type        = number
  default     = 2
}

variable "api_upload_url_ttl_seconds" {
  description = "Lifetime of a presigned upload URL."
  type        = number
  default     = 600
}

variable "abandoned_upload_expiry_days" {
  description = "Days before an unconfirmed presigned upload (tagged chordsync-upload=presigned) is expired."
  type        = number
  default     = 2

  validation {
    condition     = var.abandoned_upload_expiry_days >= 2
    error_message = "Keep at least 2 days: queued work can wait up to the 24 h queue retention."
  }
}

variable "log_retention_days" {
  description = "Retention for the API, API Gateway access, and dispatcher log groups."
  type        = number
  default     = 7
}

locals {
  api_on   = var.hosted_api_enabled
  api_name = "${local.name_prefix}-api"

  # Built from the function name (not read from the function resource), so a
  # change to the dispatcher's code never makes this IAM policy "known after apply".
  dispatcher_arn = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.dispatcher_name}"

  demo_token_parameter_path = startswith(var.demo_token_parameter_name, "/") ? var.demo_token_parameter_name : "/${var.demo_token_parameter_name}"
  demo_token_parameter_arn  = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.demo_token_parameter_path}"

  # Explicit routes only: anything else (the legacy upload path, /docs,
  # /openapi.json) is answered 404 by API Gateway without reaching Lambda.
  api_routes = [
    "GET /",
    "GET /health",
    "POST /analysis/jobs",
    "POST /analysis/jobs/{job_id}/confirm-upload",
    "POST /analysis/jobs/{job_id}/cancel",
    "GET /analysis/jobs/{job_id}",
    "GET /analysis/jobs/{job_id}/result",
  ]
  api_write_routes = [
    "POST /analysis/jobs",
    "POST /analysis/jobs/{job_id}/confirm-upload",
    "POST /analysis/jobs/{job_id}/cancel",
  ]
}

# --- Lambda concurrency reality check (a warning, never a failure) -------------

check "api_reserved_concurrency_fits_account_quota" {
  data "aws_servicequotas_service_quota" "lambda_concurrency" {
    service_code = "lambda"
    quota_code   = "L-B99A9384"
  }

  assert {
    condition     = !local.api_on || var.api_reserved_concurrency < 0 || data.aws_servicequotas_service_quota.lambda_concurrency.value - var.api_reserved_concurrency >= 10
    error_message = "Reserving ${var.api_reserved_concurrency} concurrent executions would leave fewer than the 10 AWS requires unreserved. Request a Lambda concurrency quota increase, or use api_reserved_concurrency = -1 (no reservation), before applying."
  }
}

# --- ECR: the existing API repository is reused (main.tf) ----------------------

locals {
  api_image_uri = "${aws_ecr_repository.api.repository_url}@${var.api_image_digest}"
}

# --- API Lambda role -----------------------------------------------------------

data "aws_iam_policy_document" "api_lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api_lambda" {
  count              = local.api_on ? 1 : 0
  name               = "${local.api_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.api_lambda_trust.json
}

resource "aws_cloudwatch_log_group" "api" {
  count             = local.api_on ? 1 : 0
  name              = "/aws/lambda/${local.api_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "api_lambda" {
  statement {
    sid = "SourceUploads"
    # PutObject is exercised by the browser or phone through the presigned URL,
    # which carries this role's authority. PutObjectTagging is required because
    # the signed upload carries the lifecycle tag header. GetObject also covers
    # HeadObject. DeleteObject removes rejected uploads.
    actions = [
      "s3:PutObject",
      "s3:PutObjectTagging",
      "s3:GetObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.artifacts.arn}/jobs/*/source/*"]
  }

  statement {
    sid       = "ReadTimelineResults"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/jobs/*/results/*"]
  }

  statement {
    # Lets HeadObject answer 404 for a key that is really absent instead of an
    # ambiguous 403. Bucket-level resource (ListBucket never applies to objects),
    # limited to job source prefixes. UNVERIFIED against real S3: if the HEAD
    # check does not carry s3:prefix, this does not take effect and a missing
    # object stays a 403, which the API reports as 503. See the S7-T06 document.
    sid       = "TellMissingSourceFromDenied"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["jobs/*/source/*"]
    }
  }

  statement {
    # The one parameter holding the demo-token verifier. No path or wildcard.
    sid       = "ReadDemoTokenVerifier"
    actions   = ["ssm:GetParameter"]
    resources = [local.demo_token_parameter_arn]
  }

  dynamic "statement" {
    for_each = var.demo_token_kms_key_arn != "" ? [1] : []

    content {
      sid       = "DecryptDemoTokenVerifier"
      actions   = ["kms:Decrypt"]
      resources = [var.demo_token_kms_key_arn]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["ssm.${var.aws_region}.amazonaws.com"]
      }
    }
  }

  statement {
    # The repository uses GetItem and conditional PutItem only (no UpdateItem,
    # no Scan).
    sid       = "JobState"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.jobs.arn]
  }

  statement {
    sid       = "QueueAnalysis"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.analysis.arn]
  }

  statement {
    sid       = "NudgeWorkerDispatcher"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.dispatcher_arn]
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.api_name}:*"]
  }
}

resource "aws_iam_role_policy" "api_lambda" {
  count  = local.api_on ? 1 : 0
  name   = "hosted-api"
  role   = aws_iam_role.api_lambda[0].id
  policy = data.aws_iam_policy_document.api_lambda.json
}

# --- API Lambda ----------------------------------------------------------------

resource "aws_lambda_function" "api" {
  count         = local.api_on ? 1 : 0
  function_name = local.api_name
  role          = aws_iam_role.api_lambda[0].arn
  package_type  = "Image"
  image_uri     = local.api_image_uri
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 30

  ephemeral_storage {
    size = 512
  }

  reserved_concurrent_executions = var.api_reserved_concurrency

  environment {
    variables = {
      CHORDSYNC_API_HOSTING_MODE           = "lambda"
      CHORDSYNC_RUNTIME_MODE               = "aws"
      CHORDSYNC_DISPATCH_MODE              = "queue"
      CHORDSYNC_UPLOAD_URL_TTL_SECONDS     = tostring(var.api_upload_url_ttl_seconds)
      CHORDSYNC_API_STAGING_ROOT           = "/tmp/chordsync-api"
      CHORDSYNC_S3_BUCKET                  = aws_s3_bucket.artifacts.id
      CHORDSYNC_DYNAMODB_JOB_TABLE         = aws_dynamodb_table.jobs.name
      CHORDSYNC_SQS_ANALYSIS_QUEUE_URL     = aws_sqs_queue.analysis.url
      CHORDSYNC_DEMO_TOKEN_PARAMETER       = var.demo_token_parameter_name
      CHORDSYNC_WORKER_DISPATCHER_FUNCTION = aws_lambda_function.dispatcher[0].function_name
    }
  }

  lifecycle {
    precondition {
      condition     = can(regex("^sha256:[0-9a-f]{64}$", var.api_image_digest))
      error_message = "api_image_digest must be an immutable sha256:<64 hex> digest; tags are not accepted."
    }

    precondition {
      condition     = var.demo_token_parameter_name != ""
      error_message = "The hosted API requires authentication: set demo_token_parameter_name to the SSM parameter holding the demo-token verifier."
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api_lambda]
}

# --- API Gateway HTTP API ------------------------------------------------------

resource "aws_apigatewayv2_api" "hosted" {
  count         = local.api_on ? 1 : 0
  name          = local.api_name
  protocol_type = "HTTP"
  description   = "ChordSync hosted API (HTTPS default endpoint, no custom domain, no CORS)."

  lifecycle {
    precondition {
      condition     = var.demo_token_parameter_name != ""
      error_message = "The hosted API requires authentication: set demo_token_parameter_name to the SSM parameter holding the demo-token verifier."
    }
  }
}

resource "aws_apigatewayv2_integration" "hosted" {
  count                  = local.api_on ? 1 : 0
  api_id                 = aws_apigatewayv2_api.hosted[0].id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.api[0].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "hosted" {
  for_each  = local.api_on ? toset(local.api_routes) : toset([])
  api_id    = aws_apigatewayv2_api.hosted[0].id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.hosted[0].id}"
}

resource "aws_cloudwatch_log_group" "api_access" {
  count             = local.api_on ? 1 : 0
  name              = "/aws/apigateway/${local.api_name}-access"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "hosted" {
  count       = local.api_on ? 1 : 0
  api_id      = aws_apigatewayv2_api.hosted[0].id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.api_throttle_rate_limit
    throttling_burst_limit = var.api_throttle_burst_limit
  }

  dynamic "route_settings" {
    for_each = local.api_on ? toset(local.api_write_routes) : toset([])

    content {
      route_key              = route_settings.value
      throttling_rate_limit  = var.api_write_throttle_rate_limit
      throttling_burst_limit = var.api_write_throttle_burst_limit
    }
  }

  # No request headers or bodies are logged, so tokens never reach the log.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access[0].arn
    format = jsonencode({
      requestId    = "$context.requestId"
      requestTime  = "$context.requestTime"
      httpMethod   = "$context.httpMethod"
      routeKey     = "$context.routeKey"
      status       = "$context.status"
      responseSize = "$context.responseLength"
      latencyMs    = "$context.responseLatency"
      sourceIp     = "$context.identity.sourceIp"
    })
  }

  depends_on = [aws_apigatewayv2_route.hosted]
}

resource "aws_lambda_permission" "hosted_api" {
  count         = local.api_on ? 1 : 0
  statement_id  = "AllowHostedApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.hosted[0].execution_arn}/*/*"
}

# --- Outputs -------------------------------------------------------------------

output "hosted_api_endpoint" {
  description = "HTTPS base URL for the Flutter app (empty while the hosted API is disabled)."
  value       = local.api_on ? aws_apigatewayv2_api.hosted[0].api_endpoint : ""
}

output "api_function_name" {
  description = "API Lambda function name (empty while disabled)."
  value       = local.api_on ? aws_lambda_function.api[0].function_name : ""
}

output "api_function_arn" {
  description = "API Lambda ARN (empty while disabled)."
  value       = local.api_on ? aws_lambda_function.api[0].arn : ""
}

output "api_log_group_name" {
  description = "API Lambda log group (empty while disabled)."
  value       = local.api_on ? aws_cloudwatch_log_group.api[0].name : ""
}

output "api_access_log_group_name" {
  description = "API Gateway access log group (empty while disabled)."
  value       = local.api_on ? aws_cloudwatch_log_group.api_access[0].name : ""
}
