terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.29.0, < 7.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
  # Local state (gitignored). It holds the origin secret - keep it private.
}

# No credentials in files: export AWS_PROFILE=mtls-lab
provider "aws" {
  region = var.region # must be us-east-1: CloudFront only uses ACM certs from us-east-1
  default_tags {
    tags = { Project = "mtls-lab", ManagedBy = "terraform", Purpose = "learning-lab-delete-me" }
  }
}
