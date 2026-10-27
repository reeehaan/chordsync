"""Static guards on the accounts Terraform (cognito.tf). Nothing here runs Terraform."""

from __future__ import annotations

import re
from pathlib import Path

TF = Path(__file__).resolve().parents[1] / "infrastructure/aws"
COGNITO = (TF / "cognito.tf").read_text()
API = (TF / "api.tf").read_text()
VARIABLES = (TF / "variables.tf").read_text()
OUTPUTS = (TF / "outputs.tf").read_text()


def _block(text: str, header: str) -> str:
    start = text.index(header)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += text[index] == "{"
        depth -= text[index] == "}"
        if depth == 0:
            return text[start : index + 1]
    raise AssertionError(header)


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


POOL = _code(_block(COGNITO, 'resource "aws_cognito_user_pool" "users"'))
CLIENT = _code(_block(COGNITO, 'resource "aws_cognito_user_pool_client" "app"'))


def test_accounts_are_off_unless_asked_for_so_existing_plans_do_not_change():
    assert re.search(r"default\s+= false", _block(VARIABLES, 'variable "cognito_enabled"'))
    assert re.search(r'default\s+= ""', _block(VARIABLES, 'variable "cognito_sender_email"'))
    for resource in ("aws_cognito_user_pool", "aws_cognito_user_pool_client", "aws_ses_email_identity"):
        assert re.search(rf'resource "{resource}" "\w+" \{{\s+count\s+= local.cognito_on \? 1 : 0', COGNITO)


def test_sign_in_is_an_email_code_and_accounts_are_created_without_a_password():
    # AWS requires PASSWORD in the list; EMAIL_OTP is what the app uses.
    assert 'allowed_first_auth_factors = ["PASSWORD", "EMAIL_OTP"]' in POOL
    assert "SMS_OTP" not in POOL and "WEB_AUTHN" not in POOL
    assert 'user_pool_tier      = "ESSENTIALS"' in POOL  # email codes need Essentials or higher
    assert 'username_attributes      = ["email"]' in POOL
    assert 'auto_verified_attributes = ["email"]' in POOL
    assert 'mfa_configuration   = "OFF"' in POOL
    assert 'deletion_protection = "ACTIVE"' in POOL  # an accidental destroy cannot delete accounts
    assert "allow_admin_create_user_only = false" in POOL


def test_codes_are_sent_through_ses_from_the_verified_address():
    assert 'email_sending_account = "DEVELOPER"' in POOL
    assert "aws_ses_email_identity.sender[0].arn" in POOL
    assert "var.cognito_sender_email" in _code(_block(COGNITO, 'resource "aws_ses_email_identity"'))
    assert "cognito_sender_email" in POOL and "precondition" in POOL  # enabling it without an address fails the plan


def test_the_app_client_has_no_secret_and_only_the_flows_it_needs():
    assert "generate_secret = false" in CLIENT
    flows = re.search(r"explicit_auth_flows\s*=\s*\[(.*?)\]", CLIENT, re.S).group(1)
    assert set(re.findall(r'"(\w+)"', flows)) == {"ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"}
    assert "enable_token_revocation = true" in CLIENT  # sign-out revokes the refresh token
    assert 'prevent_user_existence_errors = "ENABLED"' in CLIENT
    assert "callback_urls" not in CLIENT and "oauth" not in CLIENT  # no hosted login page


def test_access_tokens_are_short_lived_so_a_signed_out_token_dies_soon():
    assert re.search(r"access_token_validity\s+= 60\b", CLIENT)
    assert re.search(r'access_token\s+= "minutes"', CLIENT)
    assert re.search(r"refresh_token_validity\s+= 30\b", CLIENT)
    assert re.search(r'refresh_token\s+= "days"', CLIENT)


def test_the_api_gets_the_pool_and_client_ids_only_when_accounts_are_on():
    env = _block(API, "environment {")
    assert re.search(
        r"CHORDSYNC_COGNITO_USER_POOL_ID\s+= local.cognito_on \? aws_cognito_user_pool.users\[0\].id : \"\"", env
    )
    assert re.search(
        r"CHORDSYNC_COGNITO_CLIENT_ID\s+= local.cognito_on \? aws_cognito_user_pool_client.app\[0\].id : \"\"", env
    )
    assert "CHORDSYNC_DEMO_TOKEN_PARAMETER" in env  # demo tokens keep working until switched off


def test_the_api_role_gets_no_cognito_permissions_because_it_only_reads_public_keys():
    policies = "\n".join(re.findall(r'data "aws_iam_policy_document" "api_lambda".*?\n}\n', API, re.S))
    assert "cognito-idp" not in policies and "ses:" not in policies


def test_only_public_ids_are_exported():
    assert "cognito_user_pool_id" in OUTPUTS and "cognito_app_client_id" in OUTPUTS
    assert "client_secret" not in COGNITO


def test_testers_can_be_added_while_ses_is_in_the_sandbox():
    variable = _block(VARIABLES, 'variable "cognito_test_recipient_emails"')
    assert "type        = list(string)" in variable and "default     = []" in variable
    recipient = _block(COGNITO, 'resource "aws_ses_email_identity" "test_recipient"')
    assert "local.cognito_on ? toset(var.cognito_test_recipient_emails) : toset([])" in recipient
    assert "sender" not in recipient  # never confused with the one sender identity
