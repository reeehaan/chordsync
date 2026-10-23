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
  default     = "demo"

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
    Model asset release the worker installs at startup (2026.10.2 adds the
    optional multilingual aligner and 2026.10.3 the optional large BTC model for
    chord extensions; both are fetched only when a song needs them). It reads
    models/releases/<id>/manifest.json and refuses to poll the queue unless
    every required asset verifies against the manifest's SHA-256 values.
  EOT
  type        = string
  default     = "2026.10.3"

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

variable "chord_extensions_enabled" {
  description = <<-EOT
    Show 7, maj7, m7, sus2 and sus4 chords where BTC's large model and the notes
    in the instrumental audio agree (analysis/chords/extensions.py). Needs model
    release 2026.10.3 or later. Off by default: with it false, analysis is exactly
    what it was before. Switch it off again at any time with one apply, no image
    change needed.
  EOT
  type        = bool
  default     = false
}

variable "warm_workers_enabled" {
  description = <<-EOT
    Start a worker as soon as an upload begins and keep it for the next song, so
    songs skip most of the Fargate cold start (about 70 s). Costs idle worker time
    (about 4 cents per 10 minutes). Set to false to return to one-song workers.
  EOT
  type        = bool
  default     = true
}

variable "worker_initial_wait_seconds" {
  description = "How long a worker started by an upload waits for its song before exiting."
  type        = number
  default     = 120

  validation {
    condition     = var.worker_initial_wait_seconds >= 0 && var.worker_initial_wait_seconds <= 900
    error_message = "worker_initial_wait_seconds must be between 0 and 900."
  }
}

variable "worker_linger_seconds" {
  description = "How long a worker stays idle after a song, waiting for the next one."
  type        = number
  default     = 300

  validation {
    condition     = var.worker_linger_seconds >= 0 && var.worker_linger_seconds <= 3600
    error_message = "worker_linger_seconds must be between 0 and 3600."
  }
}
