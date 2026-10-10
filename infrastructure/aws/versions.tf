terraform {
  required_version = ">= 1.6.0"

  backend "s3" {
    bucket       = "chordsync-rehan-student-terraform-state-sg"
    key          = "chordsync/dev/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
