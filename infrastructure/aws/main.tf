locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

data "aws_partition" "current" {}

resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${local.name_prefix}-artifacts-"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Suspended"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  depends_on = [aws_s3_bucket_versioning.artifacts]

  rule {
    id     = "expire-successful-source"
    status = "Enabled"

    filter {
      and {
        prefix = "jobs/"
        tags = {
          "chordsync-expire-source" = "true"
        }
      }
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "expire-debug-artifacts"
    status = "Enabled"

    filter {
      and {
        prefix = "jobs/"
        tags = {
          "chordsync-artifact-role" = "debug"
        }
      }
    }

    expiration {
      days = 7
    }
  }

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "artifacts_https_only" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts_https_only" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts_https_only.json
}

resource "aws_dynamodb_table" "jobs" {
  name         = "${local.name_prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"

  attribute {
    name = "PK"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = false
  }

  deletion_protection_enabled = false
}

resource "aws_sqs_queue" "analysis_dlq" {
  name                      = "${local.name_prefix}-analysis-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "analysis" {
  name                       = "${local.name_prefix}-analysis"
  message_retention_seconds  = 86400
  visibility_timeout_seconds = var.analysis_visibility_timeout_seconds
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.analysis_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_ecr_repository" "api" {
  name                 = "${local.name_prefix}/api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "worker" {
  name                 = "${local.name_prefix}/worker"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name
  policy     = local.ecr_lifecycle_policy
}

locals {
  ecr_lifecycle_policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Remove untagged images after seven days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 7
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "analysis" {
  name = "${local.name_prefix}-analysis"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/chordsync/${var.environment}/worker"
  retention_in_days = 7
}

locals {
  # Digest reference only: a re-pushed tag can never change what the task runs.
  worker_image = "${aws_ecr_repository.worker.repository_url}@${var.worker_image_digest}"
}

resource "aws_ecs_task_definition" "worker" {
  family = "${local.name_prefix}-worker"
  # CPU-only runs use Fargate so a one-shot RunTask needs no EC2 capacity.
  # GPU requirements are only schedulable on EC2 container instances.
  requires_compatibilities = var.worker_gpu_count > 0 ? ["EC2"] : ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.worker_cpu_units)
  memory                   = tostring(var.worker_memory_mib)
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name      = "analysis-worker"
    image     = local.worker_image
    essential = true
    # One delivery per task: exits after one job or one empty 20 s long poll.
    command = ["python", "-m", "backend.api.app.analysis_worker_consumer", "--once"]
    environment = [
      { name = "CHORDSYNC_RUNTIME_MODE", value = "aws" },
      { name = "CHORDSYNC_DISPATCH_MODE", value = "queue" },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "CHORDSYNC_S3_BUCKET", value = aws_s3_bucket.artifacts.id },
      { name = "CHORDSYNC_DYNAMODB_JOB_TABLE", value = aws_dynamodb_table.jobs.name },
      { name = "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL", value = aws_sqs_queue.analysis.url },
      # Paths below match the approved image layout; set explicitly so the
      # deployment does not silently depend on image defaults.
      { name = "CHORDSYNC_WORKSPACE_ROOT", value = "/tmp/chordsync" },
      { name = "CHORDSYNC_BTC_PYTHON", value = "/opt/chordsync/venvs/btc/bin/python" },
      { name = "CHORDSYNC_BTC_SOURCE", value = "/opt/chordsync/models/btc/source" },
      { name = "CHORDSYNC_BTC_CHECKPOINT", value = "/opt/chordsync/models/btc/btc_model.pt" },
      { name = "CHORDSYNC_BEAT_PYTHON", value = "/opt/chordsync/venvs/beats/bin/python" },
      { name = "CHORDSYNC_WHISPERX_EXECUTABLE", value = "/opt/chordsync/venvs/whisperx/bin/whisperx" },
      { name = "CHORDSYNC_DEMUCS_EXECUTABLE", value = "/opt/chordsync/venvs/demucs/bin/demucs" },
      { name = "XDG_CACHE_HOME", value = "/opt/chordsync/cache" },
      { name = "HF_HOME", value = "/opt/chordsync/cache/huggingface" },
      { name = "TORCH_HOME", value = "/opt/chordsync/cache/torch" },
      # Models come only from the staged private cache; fail fast instead of
      # attempting uncontrolled Hugging Face downloads.
      { name = "HF_HUB_OFFLINE", value = "1" },
      # Bootstrap installs and verifies this release before polling the queue.
      { name = "CHORDSYNC_MODEL_RELEASE", value = var.model_release_id },
      { name = "CHORDSYNC_MODEL_MANIFEST_KEY", value = "models/releases/${var.model_release_id}/manifest.json" },
    ]
    resourceRequirements = var.worker_gpu_count > 0 ? [{
      type  = "GPU"
      value = tostring(var.worker_gpu_count)
    }] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.worker.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}
