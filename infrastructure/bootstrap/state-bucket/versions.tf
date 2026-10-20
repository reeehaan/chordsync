terraform {
  required_version = ">= 1.10.0"

  backend "s3" {
    bucket       = "chordsync-rehan-student-terraform-state-sg"
    key          = "chordsync/bootstrap/state-bucket.tfstate"
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
  region = "ap-southeast-1"
}
