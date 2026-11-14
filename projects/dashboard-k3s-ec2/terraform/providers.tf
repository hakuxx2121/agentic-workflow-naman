# No credentials here. The AWS provider uses the default credential chain:
# export AWS_PROFILE=dashboard-admin (a fresh key / SSO profile you set up yourself, see README step 1).
provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

data "aws_availability_zones" "available" {
  state = "available"
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

data "aws_caller_identity" "current" {}

locals {
  name = var.name
  # The ALB needs subnets in two different AZs. The k3s node lives in the first one.
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  tags = {
    Project   = "dashboard-k3s-ec2"
    ManagedBy = "terraform"
    Owner     = var.owner
  }
}
