terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
  }

  # Default: LOCAL state (terraform.tfstate in this folder). It is gitignored.
  # State holds resource IDs and the publisher user's ARN, but no secrets: Terraform never creates an access key here.
}
