terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
  }

  # Default: LOCAL state (a terraform.tfstate file in this folder).
  # To use S3 instead, copy backend.tf.example to backend.tf and re-run `terraform init -migrate-state`.
}
