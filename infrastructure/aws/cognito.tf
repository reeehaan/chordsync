# --- Accounts: Amazon Cognito user pool with email one-time-code sign-in ------
#
# Users sign in with their email and a 6-digit code, no password. The app calls
# Cognito directly with its own screens; there is no hosted login page. The API
# checks the access token itself (backend/api/app/cognito_auth.py).
#
# Off by default, so a plan that does not set cognito_enabled changes nothing.
# Email codes are sent through Amazon SES from one verified address. A new SES
# account is in the sandbox: it can email only addresses verified in SES, until
# production access is requested in the console.

locals {
  cognito_on   = var.cognito_enabled
  cognito_name = "${local.name_prefix}-users"
}

resource "aws_ses_email_identity" "sender" {
  count = local.cognito_on ? 1 : 0
  email = var.cognito_sender_email
}

resource "aws_cognito_user_pool" "users" {
  count = local.cognito_on ? 1 : 0
  name  = local.cognito_name

  # Email one-time codes need the Essentials plan or higher.
  user_pool_tier      = "ESSENTIALS"
  deletion_protection = "ACTIVE"
  mfa_configuration   = "OFF"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  username_configuration {
    case_sensitive = false
  }

  # AWS refuses a pool without PASSWORD here ("Password should be configured as
  # one of the allowed first auth factors"). Accounts are created without a
  # password and the app only ever asks for EMAIL_OTP, so nobody has a password
  # unless they run Cognito's forgot-password flow, which also needs a code sent
  # to their own inbox.
  sign_in_policy {
    allowed_first_auth_factors = ["PASSWORD", "EMAIL_OTP"]
  }

  # Anyone with the app can create an account; nobody is created by an admin.
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 5
      max_length = 254
    }
  }

  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = aws_ses_email_identity.sender[0].arn
    from_email_address    = "ChordSync <${var.cognito_sender_email}>"
  }

  lifecycle {
    precondition {
      condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.cognito_sender_email))
      error_message = "cognito_enabled needs cognito_sender_email: the SES-verified address the sign-in codes are sent from."
    }
  }
}

resource "aws_cognito_user_pool_client" "app" {
  count        = local.cognito_on ? 1 : 0
  name         = "${local.cognito_name}-mobile"
  user_pool_id = aws_cognito_user_pool.users[0].id

  # A mobile app cannot keep a secret, so there is none.
  generate_secret = false

  # Choice-based sign-in (email code), plus silent renewal of the session.
  explicit_auth_flows = ["ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  # Short access tokens: a signed-out or deleted user's token dies within the hour.
  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  # Sign-out revokes the refresh token on the server.
  enable_token_revocation = true

  # An unknown email and a known one look the same to the caller.
  prevent_user_existence_errors = "ENABLED"

  read_attributes  = ["email", "email_verified"]
  write_attributes = ["email"]
}
