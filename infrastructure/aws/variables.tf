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

variable "worker_image_tag" {
  description = "Worker image tag used by the task-definition skeleton."
  type        = string
  default     = "latest"
}

variable "worker_cpu_units" {
  description = "ECS CPU units reserved by the worker task skeleton."
  type        = number
  default     = 4096
}

variable "worker_memory_mib" {
  description = "Memory reserved by the worker task skeleton."
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

variable "budget_alert_email" {
  description = "Optional email address for AWS Budget alerts. Empty disables the budget resource."
  type        = string
  default     = ""
  sensitive   = true
}
