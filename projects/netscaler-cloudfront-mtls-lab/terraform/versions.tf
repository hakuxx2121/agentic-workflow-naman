terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # aws_lb_trust_store / mutual_authentication: 5.x+.
      # aws_cloudfront_trust_store: 6.27.0. viewer_mtls_config on aws_cloudfront_distribution: 6.29.0.
      version = ">= 6.29.0, < 7.0.0"
    }
  }

  # Default: LOCAL state (terraform.tfstate in this folder, gitignored).
  # It contains the lab server private key that was imported into ACM - treat it as secret.
}
