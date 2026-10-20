# A protected second copy of the model files (the `models/` folder of the artifacts
# bucket). Nothing in the main stack references this bucket, so a rename or replace
# there cannot touch it.

data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  bucket_name = "chordsync-model-backup-${local.account_id}"

  # Only these may delete versions, suspend versioning or delete the bucket.
  admin_principals = [
    "arn:aws:iam::${local.account_id}:role/ChordSyncTerraformRole",
    "arn:aws:iam::${local.account_id}:user/rehan",
    "arn:aws:iam::${local.account_id}:root",
  ]
}

resource "aws_s3_bucket" "backup" {
  bucket        = local.bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket                  = aws_s3_bucket.backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

data "aws_iam_policy_document" "backup" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.backup.arn,
      "${aws_s3_bucket.backup.arn}/*",
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
      aws_s3_bucket.backup.arn,
      "${aws_s3_bucket.backup.arn}/*",
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

resource "aws_s3_bucket_policy" "backup" {
  bucket = aws_s3_bucket.backup.id
  policy = data.aws_iam_policy_document.backup.json

  depends_on = [
    aws_s3_bucket_public_access_block.backup,
    aws_s3_bucket_versioning.backup,
  ]
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  # The bucket must be versioned before a noncurrent-version rule applies.
  depends_on = [aws_s3_bucket_versioning.backup]

  rule {
    id     = "keep-recent-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days           = 365
      newer_noncurrent_versions = 3
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

output "backup_bucket" {
  value = aws_s3_bucket.backup.bucket
}
