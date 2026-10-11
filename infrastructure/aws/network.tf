# Network for one-shot Fargate worker tasks: public default-VPC subnets with a
# public IP and an egress-only security group. No NAT, no load balancer, and no
# inbound rules. See docs/cloud/s6-t13-model-bootstrap.md.

data "aws_vpc" "default" {
  default = true
}

# Default-for-AZ subnets route 0.0.0.0/0 to the VPC internet gateway through
# the main route table (verified 2026-10-11; no explicit associations).
data "aws_subnets" "worker_public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "analysis_worker" {
  name        = "chordsync-analysis-worker"
  description = "ChordSync analysis worker: no inbound, HTTPS egress to AWS APIs only"
  vpc_id      = data.aws_vpc.default.id

  # Explicitly empty: Terraform removes any inbound rule added outside it.
  ingress = []

  egress {
    description = "HTTPS to ECR, S3, SQS, DynamoDB, and CloudWatch Logs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "chordsync-analysis-worker"
  }
}
