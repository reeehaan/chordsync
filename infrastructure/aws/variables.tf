variable "aws_region" {
  description = "AWS region for the single-region student deployment."
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Lowercase name used in resource names."
  type        = string
  default     = "chordsync"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "project_name must contain only lowercase letters, digits, and hyphens."
  }
}

variable "environment" {
  description = "Short deployment environment name."
  type        = string
  default     = "student-demo"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.environment))
    error_message = "environment must contain only lowercase letters, digits, and hyphens."
  }
}

variable "worker_image_digest" {
  description = <<-EOT
    Content digest of the approved ARM64 worker image in the worker ECR
    repository. Tags are deliberately not accepted: the task definition must
    reference one immutable, scanned image. Changing this value requires a
    matching approved entry in docs/security/container-exceptions.md.
  EOT
  type        = string
  # worker-d9ef4a3-runtime2; CRITICAL-finding exception expires 2026-11-09.
  default = "sha256:0330563b60f5113395906467c0d1b7dfad6a654675e22f4c56ff928bd53c99aa"

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.worker_image_digest))
    error_message = "worker_image_digest must be an exact sha256 digest, not a tag."
  }
}

variable "model_release_id" {
  description = <<-EOT
    Model asset release the worker installs at startup. The worker reads
    models/releases/<id>/manifest.json and refuses to poll the queue unless
    every required asset verifies against the manifest's SHA-256 values.
  EOT
  type        = string
  default     = "2026.10.1"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]{0,63}$", var.model_release_id))
    error_message = "model_release_id must be 1-64 lowercase letters, digits, '.', '_' or '-'."
  }
}

variable "worker_cpu_units" {
  description = "ECS CPU units for the CPU-only ARM64 worker (4096 = 4 vCPU)."
  type        = number
  default     = 4096
}

variable "worker_memory_mib" {
  description = "Memory for the worker task; 16 GiB is valid with 4 vCPU on Fargate."
  type        = number
  default     = 16384
}

variable "worker_gpu_count" {
  description = "GPU resource requirement; keep zero until the AWS benchmark selects capacity."
  type        = number
  default     = 0

  validation {
    condition     = var.worker_gpu_count >= 0 && floor(var.worker_gpu_count) == var.worker_gpu_count
    error_message = "worker_gpu_count must be a non-negative integer."
  }
}

variable "analysis_visibility_timeout_seconds" {
  description = "Temporary conservative SQS visibility timeout pending Linux/AWS benchmarking."
  type        = number
  default     = 1200

  validation {
    condition     = var.analysis_visibility_timeout_seconds >= 900 && var.analysis_visibility_timeout_seconds <= 43200
    error_message = "Visibility timeout must be between 15 minutes and 12 hours."
  }
}

variable "alert_email" {
  description = "Optional email address for budget alerts and operational alarms. Empty creates the budget and alert topic without any subscriber, so nothing is delivered until it is set (the SNS subscription must also be confirmed from that inbox)."
  type        = string
  default     = ""
  sensitive   = true
}
