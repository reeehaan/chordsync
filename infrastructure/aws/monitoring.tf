resource "aws_cloudwatch_metric_alarm" "analysis_queue_depth" {
  alarm_name          = "${local.name_prefix}-analysis-queue-depth"
  alarm_description   = "Analysis work has remained queued for at least 15 minutes."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.analysis.name
  }
}

resource "aws_cloudwatch_metric_alarm" "analysis_dlq_nonempty" {
  alarm_name          = "${local.name_prefix}-analysis-dlq-nonempty"
  alarm_description   = "At least one analysis delivery reached the dead-letter queue."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.analysis_dlq.name
  }
}

resource "aws_budgets_budget" "monthly" {
  count = var.budget_alert_email == "" ? 0 : 1

  name         = "${local.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = "20"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = toset([50, 80, 100])
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }
}
