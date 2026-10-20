# Adds a policy and lifecycle to the Terraform state bucket. The bucket itself was
# created by hand, so it is referenced, not managed: Terraform only adds the two
# settings below and can never delete the bucket.

locals {
  state_bucket = "chordsync-rehan-student-terraform-state-sg"
  account_id   = data.aws_caller_identity.current.account_id

  # Only these may delete state versions, suspend versioning or delete the bucket.
  admin_principals = [
    "arn:aws:iam::${local.account_id}:role/ChordSyncTerraformRole",
    "arn:aws:iam::${local.account_id}:user/rehan",
    "arn:aws:iam::${local.account_id}:root",
  ]
}

data "aws_caller_identity" "current" {}

data "aws_s3_bucket" "state" {
  bucket = local.state_bucket
}

data "aws_iam_policy_document" "state" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      data.aws_s3_bucket.state.arn,
      "${data.aws_s3_bucket.state.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyDestructiveActionsExceptAdmins"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:DeleteObjectVersion",
      "s3:PutBucketVersioning",
    ]
    resources = [
      data.aws_s3_bucket.state.arn,
      "${data.aws_s3_bucket.state.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnNotLike"
      variable = "aws:PrincipalArn"
      values   = local.admin_principals
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = data.aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state.json
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = data.aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    # Keep the newest 20 old versions of each file, and nothing older than 90 days.
    noncurrent_version_expiration {
      noncurrent_days           = 90
      newer_noncurrent_versions = 20
    }

    # Remove delete markers left behind once nothing sits under them.
    expiration {
      expired_object_delete_marker = true
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
