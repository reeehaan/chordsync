"""Static guards on the hosted-API Terraform (S7-T05). Nothing here runs Terraform."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TF = Path(__file__).resolve().parents[1] / "infrastructure/aws"
API = (TF / "api.tf").read_text()
DISPATCHER = (TF / "dispatcher.tf").read_text()
MAIN = (TF / "main.tf").read_text()
ALL_TF = {path.name: path.read_text() for path in TF.glob("*.tf")}


def _block(text: str, header: str) -> str:
    start = text.index(header)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += text[index] == "{"
        depth -= text[index] == "}"
        if depth == 0:
            return text[start : index + 1]
    raise AssertionError(header)


def _policy(name: str) -> str:
    """Policy text without comments (comments may name what is absent)."""
    text = _block(API, f'data "aws_iam_policy_document" "{name}"')
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _list(text: str, header: str) -> str:
    start = text.index(header)
    return text[start : text.index("]", start)]


def test_the_hosted_api_is_off_by_default():
    variable = _block(API, 'variable "hosted_api_enabled"')
    assert "default     = false" in variable
    assert "hosted_api_acknowledge_no_auth" not in "".join(ALL_TF.values())  # escape hatch removed


def test_every_hosted_resource_is_gated_by_the_flag():
    for name, text in (("api.tf", API), ("dispatcher.tf", DISPATCHER)):
        for block in text.split('\nresource "')[1:]:
            header = block.split("\n}\n")[0]
            assert "count" in header or "for_each" in header, f"{name}: {block[:70]}"
            assert re.search(r"local\.(api_on|dispatcher_on|dispatcher_schedule_on)", header), block[:70]


def test_the_hosted_api_cannot_plan_without_auth_configuration():
    for header in ('resource "aws_apigatewayv2_api" "hosted"', 'resource "aws_lambda_function" "api"'):
        block = _block(API, header)
        assert "precondition" in block
        assert 'var.demo_token_parameter_name != ""' in block
    variable = _block(API, 'variable "demo_token_parameter_name"')
    assert 'default     = ""' in variable and "regex" in variable


def test_the_lambda_uses_an_immutable_digest_never_a_tag():
    assert 'repository_url}@${var.api_image_digest}' in API
    assert "sha256:" in _block(API, 'resource "aws_lambda_function" "api"')
    assert ":latest" not in "".join(ALL_TF.values())
    function = _block(API, 'resource "aws_lambda_function" "api"')
    for expected in (
        'package_type  = "Image"',
        'architectures = ["arm64"]',
        "memory_size   = 512",
        "timeout       = 30",
        "size = 512",
        "reserved_concurrent_executions = var.api_reserved_concurrency",
    ):
        assert expected in function, expected


def test_the_existing_api_repository_is_reused_not_duplicated():
    assert MAIN.count('resource "aws_ecr_repository" "api"') == 1
    assert 'resource "aws_ecr_repository"' not in API


def test_the_api_environment_has_no_credentials_or_secrets():
    env = _block(API, "environment {")
    assert re.search(r'CHORDSYNC_API_HOSTING_MODE\s+= "lambda"', env)
    assert re.search(r'CHORDSYNC_RUNTIME_MODE\s+= "aws"', env)
    assert re.search(r'CHORDSYNC_API_STAGING_ROOT\s+= "/tmp/chordsync-api"', env)
    assert re.search(r"CHORDSYNC_DEMO_TOKEN_PARAMETER\s+= var.demo_token_parameter_name", env)
    for expected in (
        "CHORDSYNC_UPLOAD_URL_TTL_SECONDS",
        "CHORDSYNC_WORKER_DISPATCHER_FUNCTION",
        "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL",
        "CHORDSYNC_DYNAMODB_JOB_TABLE",
        "CHORDSYNC_S3_BUCKET",
    ):
        assert expected in env, expected
    # the only auth value is the parameter *name*, never a token or verifier
    without_name = env.replace("CHORDSYNC_DEMO_TOKEN_PARAMETER", "")
    for forbidden in ("ACCESS_KEY", "SECRET", "TOKEN", "PASSWORD", "AWS_REGION", "sha256"):
        assert forbidden not in without_name


def test_the_api_policy_is_exactly_the_intended_set():
    policy = _policy("api_lambda")
    action_lists = re.findall(r"actions\s*=\s*\[(.*?)\]", policy, re.DOTALL)
    actions = set(re.findall(r'"([a-z0-9]+:[A-Za-z*]+)"', " ".join(action_lists)))
    assert actions == {
        "s3:PutObject", "s3:PutObjectTagging", "s3:GetObject", "s3:DeleteObject",
        "s3:ListBucket",
        "ssm:GetParameter",
        "kms:Decrypt",  # only inside the optional customer-managed-key statement
        "dynamodb:GetItem", "dynamodb:PutItem",
        "sqs:SendMessage",
        "lambda:InvokeFunction",
        "logs:CreateLogStream", "logs:PutLogEvents",
    }
    for forbidden in (
        "s3:*", "ecs:", "iam:", "models/", "UpdateItem", "Scan", "lambda:*",
        "ssm:*", "GetParametersByPath", "GetParameters\"", "secretsmanager", "kms:*",
    ):
        assert forbidden not in policy, forbidden
    assert 'resources = ["*"]' not in policy
    # source prefix: the object statement and the ListBucket prefix condition
    assert policy.count("jobs/*/source/*") == 2 and policy.count("jobs/*/results/*") == 1
    assert "resources = [local.dispatcher_arn]" in policy  # only the dispatcher
    assert re.search(
        r'dispatcher_arn = "arn:aws:lambda:\$\{var.aws_region\}:\$\{data.aws_caller_identity.current.account_id\}:function:\$\{local.dispatcher_name\}"',
        API,
    )
    # not read from the function resource: its changes must not defer the policy
    assert "aws_lambda_function.dispatcher" not in policy


def test_api_gateway_is_a_plain_https_http_api():
    assert 'protocol_type = "HTTP"' in API
    assert "cors_configuration" not in API
    assert "aws_apigatewayv2_domain_name" not in API
    assert "aws_lambda_function_url" not in "".join(ALL_TF.values())
    assert 'integration_type       = "AWS_PROXY"' in API
    assert 'payload_format_version = "2.0"' in API
    assert 'name        = "$default"' in API


def test_only_the_hosted_routes_are_exposed():
    routes = set(re.findall(r'^\s+"((?:GET|POST) [^"]+)",', _list(API, "api_routes = ["), re.MULTILINE))
    assert routes == {
        "GET /",
        "GET /health",
        "POST /analysis/jobs",
        "POST /analysis/jobs/{job_id}/confirm-upload",
        "POST /analysis/jobs/{job_id}/cancel",
        "GET /analysis/jobs/{job_id}",
        "GET /analysis/jobs/{job_id}/result",
    }
    assert "$default" not in _list(API, "api_routes = [")  # no catch-all route
    assert "audio/upload" not in API  # the legacy multipart route never reaches Lambda


def test_throttling_is_conservative_and_stricter_for_writes():
    def default(name):
        return int(re.search(r"default\s+= (\d+)", _block(API, f'variable "{name}"')).group(1))

    assert (default("api_throttle_rate_limit"), default("api_throttle_burst_limit")) == (2, 5)
    assert (default("api_write_throttle_rate_limit"), default("api_write_throttle_burst_limit")) == (1, 2)
    assert re.search(r"default\s+= -1", _block(API, 'variable "api_reserved_concurrency"'))
    assert "throttling_rate_limit" in _block(API, 'resource "aws_apigatewayv2_stage"')


def test_log_groups_have_finite_retention():
    assert "default     = 7" in _block(API, 'variable "log_retention_days"')
    for text in (API, DISPATCHER):
        for block in text.split('\nresource "aws_cloudwatch_log_group"')[1:]:
            assert "retention_in_days = var.log_retention_days" in block.split("\n}\n")[0]


def test_access_logs_do_not_record_headers_or_bodies():
    stage = _block(API, 'resource "aws_apigatewayv2_stage"')
    for forbidden in ("$context.authorizer", "request.header", "requestBody", "Authorization"):
        assert forbidden not in stage


def test_abandoned_upload_cleanup_only_matches_tagged_source_uploads():
    rule = _block(MAIN, 'dynamic "rule"')
    assert 'id     = "expire-abandoned-source-uploads"' in rule
    assert 'prefix = "jobs/"' in rule and '"chordsync-upload" = "presigned"' in rule
    assert "var.abandoned_upload_expiry_days" in rule and "var.hosted_api_enabled" in rule
    assert re.search(r"default\s+= 2", _block(API, 'variable "abandoned_upload_expiry_days"'))
    for protected in ("playback", "results", "models"):
        assert protected not in rule


def test_nothing_always_on_or_costly_is_declared():
    joined = "".join(ALL_TF.values())
    for forbidden in (
        'resource "aws_ecs_service"', 'resource "aws_nat_gateway"', 'resource "aws_lb"',
        'resource "aws_alb"', 'resource "aws_instance"', 'resource "aws_eip"',
        'resource "aws_vpc_endpoint"', "provisioned_concurrent_executions",
    ):
        assert forbidden not in joined, forbidden


def test_outputs_expose_no_secrets():
    outputs = re.findall(r'output "([a-z_]+)"', API + DISPATCHER)
    assert {"hosted_api_endpoint", "api_function_name", "api_function_arn", "dispatcher_function_arn"} <= set(outputs)
    for name in outputs:
        assert not re.search(r"secret|token|password|key", name)


@pytest.mark.parametrize("digest", ["latest", "sha256:abc", "", "sha256:" + "g" * 64])
def test_the_digest_pattern_rejects_tags_and_malformed_digests(digest):
    pattern = re.compile(r"^sha256:[0-9a-f]{64}$")
    assert not pattern.match(digest)
    assert pattern.match("sha256:" + "a" * 64)


def test_list_bucket_is_bucket_level_and_prefix_limited():
    policy = _policy("api_lambda")
    statement = _block(policy, 'sid       = "TellMissingSourceFromDenied"')
    assert 'actions   = ["s3:ListBucket"]' in statement
    # bucket ARN only: never "/*" (an object resource), never a wildcard
    assert "resources = [aws_s3_bucket.artifacts.arn]" in statement
    assert '/*"' not in statement.split("condition")[0] and '"*"' not in statement
    condition = _block(statement, "condition {")
    assert 'test     = "StringLike"' in condition  # not "...IfExists": no fail-open
    assert 'variable = "s3:prefix"' in condition
    assert 'values   = ["jobs/*/source/*"]' in condition
    assert "IfExists" not in statement
    assert policy.count("s3:ListBucket") == 1  # nowhere else, no second grant


def test_only_one_ssm_parameter_is_readable():
    policy = _policy("api_lambda")
    statement = _block(policy, 'sid       = "ReadDemoTokenVerifier"')
    assert 'actions   = ["ssm:GetParameter"]' in statement
    assert "resources = [local.demo_token_parameter_arn]" in statement
    arn = re.search(r"demo_token_parameter_arn\s+= (.+)", API).group(1)
    assert arn.endswith("parameter${local.demo_token_parameter_path}\"") and "*" not in arn
    assert "ssm:GetParameter" not in DISPATCHER  # the dispatcher has no secrets access


def test_kms_decrypt_exists_only_for_an_explicit_key_and_only_via_ssm():
    policy = _policy("api_lambda")
    block = _block(policy, 'dynamic "statement"')
    assert 'var.demo_token_kms_key_arn != "" ? [1] : []' in block
    assert "resources = [var.demo_token_kms_key_arn]" in block
    assert 'kms:ViaService' in block and "ssm." in block
    assert 'default     = ""' in _block(API, 'variable "demo_token_kms_key_arn"')


def test_reserved_concurrency_defaults_to_none_and_rejects_zero():
    variable = _block(API, 'variable "api_reserved_concurrency"')
    assert re.search(r"default\s+= -1", variable)
    assert "var.api_reserved_concurrency == -1 || var.api_reserved_concurrency >= 1" in variable
    assert "0 is rejected" in variable
    check = _block(API, 'check "api_reserved_concurrency_fits_account_quota"')
    assert "var.api_reserved_concurrency < 0" in check  # -1 never trips the quota warning


def test_the_dispatcher_terraform_has_no_user_auth():
    for word in ("demo_token", "ssm:", "bearer"):
        assert word not in DISPATCHER.casefold()
