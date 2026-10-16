output "aws_region" {
  description = "Set as AWS_REGION."
  value       = var.aws_region
}

output "chordsync_s3_bucket" {
  description = "Set as CHORDSYNC_S3_BUCKET."
  value       = aws_s3_bucket.artifacts.id
}

output "chordsync_dynamodb_job_table" {
  description = "Set as CHORDSYNC_DYNAMODB_JOB_TABLE."
  value       = aws_dynamodb_table.jobs.name
}

output "chordsync_sqs_analysis_queue_url" {
  description = "Set as CHORDSYNC_SQS_ANALYSIS_QUEUE_URL."
  value       = aws_sqs_queue.analysis.url
}

output "worker_task_definition_arn" {
  description = "Worker task-definition skeleton; no service or capacity is created."
  value       = aws_ecs_task_definition.worker.arn
}

output "worker_security_group_id" {
  description = "Egress-only security group for worker RunTask network configuration."
  value       = aws_security_group.analysis_worker.id
}

output "worker_task_subnet_ids" {
  description = "Public default-VPC subnets for worker RunTask (assignPublicIp=ENABLED)."
  value       = data.aws_subnets.worker_public.ids
}

output "worker_ecr_repository_url" {
  description = "Private worker image repository URL."
  value       = aws_ecr_repository.worker.repository_url
}
