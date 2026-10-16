"""Static guards on the account-hardening Terraform (S7-T10). Nothing here runs Terraform."""

from __future__ import annotations

import re
from pathlib import Path

TF = Path(__file__).resolve().parents[1] / "infrastructure/aws"
H = (TF / "hardening.tf").read_text()
MON = (TF / "monitoring.tf").read_text()


def _block(text: str, header: str) -> str:
    start = text.index(header)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += text[index] == "{"
        depth -= text[index] == "}"
        if depth == 0:
            return text[start : index + 1]
    raise AssertionError(header)


def test_the_budget_always_exists_and_alerts_only_with_an_address():
    budget = _block(H, 'resource "aws_budgets_budget" "monthly"')
    assert "count" not in budget.split("dynamic")[0]  # tracked even without an email
    assert budget.count('var.alert_email == "" ? []') == 2  # every notification is gated
    assert re.search(r"budget_actual_alerts\s*=\s*\[25, 50, 80, 100\]", H)
    assert 'notification_type          = "FORECASTED"' in budget
    assert "default     = 20" in _block(H, 'variable "monthly_budget_usd"')
    assert "alert_email" in (TF / "variables.tf").read_text()
    assert "budget_alert_email" not in H + MON


def test_no_email_address_is_hard_coded_anywhere():
    for path in TF.glob("*.tf"):
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", path.read_text()), path.name


def test_the_email_subscription_exists_only_with_an_address():
    sub = _block(H, 'resource "aws_sns_topic_subscription" "alerts_email"')
    assert 'var.alert_email == "" ? 0 : 1' in sub and 'protocol  = "email"' in sub


def test_every_alarm_notifies_the_topic():
    for text in (H, MON):
        for block in text.split('\nresource "aws_cloudwatch_metric_alarm"')[1:]:
            assert "alarm_actions" in block.split("\n}\n")[0] and "aws_sns_topic.alerts.arn" in block.split("\n}\n")[0]


def test_alarm_set_is_the_intended_small_one():
    names = set(re.findall(r'resource "aws_cloudwatch_metric_alarm" "(\w+)"', H + MON))
    assert names == {
        "analysis_queue_depth", "analysis_dlq_nonempty", "api_lambda_errors",
        "dispatcher_lambda_errors", "dispatcher_failures", "worker_start_burst",
    }  # no throttle, latency, or per-4xx alarms: they would be noise at this scale
    assert len(names) <= 10  # stays inside the CloudWatch free tier


def test_the_topic_only_accepts_cloudwatch_and_eventbridge_from_this_account():
    policy = _block(H, 'data "aws_iam_policy_document" "alerts_topic"')
    assert '"cloudwatch.amazonaws.com", "events.amazonaws.com"' in policy
    assert "aws:SourceAccount" in policy and 'actions   = ["sns:Publish"]' in policy


def test_cloudtrail_is_management_events_only_and_cheap():
    trail = _block(H, 'resource "aws_cloudtrail" "management"')
    assert "is_multi_region_trail         = true" in trail
    assert "enable_log_file_validation    = true" in trail
    assert "include_management_events = true" in trail
    for expensive in ("data_resource", "insight_selector", "cloud_watch_logs", "kms_key_id", "advanced_event_selector"):
        assert expensive not in trail, expensive
    assert re.search(r"default\s+= 90", _block(H, 'variable "cloudtrail_log_retention_days"'))


def test_the_trail_bucket_is_private_encrypted_and_https_only():
    for resource in ("aws_s3_bucket_public_access_block", "aws_s3_bucket_server_side_encryption_configuration",
                     "aws_s3_bucket_ownership_controls", "aws_s3_bucket_lifecycle_configuration"):
        assert f'resource "{resource}" "cloudtrail"' in H
    pab = _block(H, 'resource "aws_s3_bucket_public_access_block" "cloudtrail"')
    assert pab.count("= true") == 4  # all four public-access blocks
    policy = _block(H, 'data "aws_iam_policy_document" "cloudtrail_bucket"')
    assert "aws:SecureTransport" in policy and "aws:SourceArn" in policy
    assert '"*"' in policy and policy.count("cloudtrail.amazonaws.com") == 2  # only CloudTrail writes
    assert "force_destroy = false" in _block(H, 'resource "aws_s3_bucket" "cloudtrail"')


def test_the_mfa_guard_is_off_by_default_and_keeps_role_assumption_working():
    assert re.search(r"default\s+= false", _block(H, 'variable "enforce_admin_mfa"'))
    for resource in ('aws_iam_policy" "require_mfa"', 'aws_iam_group_policy_attachment" "require_mfa"'):
        assert "var.enforce_admin_mfa ? 1 : 0" in _block(H, f'resource "{resource}')
    policy = _block(H, 'data "aws_iam_policy_document" "require_mfa"')
    deny = _block(policy, 'sid    = "DenyEverythingElseWithoutMfa"')
    for kept in ("sts:AssumeRole", "iam:EnableMFADevice", "iam:CreateVirtualMFADevice", "iam:ChangePassword"):
        assert kept in deny, kept  # excluded from the deny, so no lockout path
    assert "BoolIfExists" in deny and "aws:MultiFactorAuthPresent" in deny


def test_the_password_policy_never_expires_existing_passwords():
    policy = _block(H, 'resource "aws_iam_account_password_policy" "baseline"')
    assert "max_password_age               = 0" in policy and "hard_expiry                    = false" in policy
    assert "allow_users_to_change_password = true" in policy


def test_hardening_adds_no_application_or_costly_infrastructure():
    for forbidden in ('resource "aws_ecs_service"', 'resource "aws_nat_gateway"', 'resource "aws_lb"',
                      'resource "aws_instance"', 'resource "aws_vpc_endpoint"', 'resource "aws_iam_user"',
                      'resource "aws_iam_access_key"', 'resource "aws_kms_key"'):
        assert forbidden not in H, forbidden
