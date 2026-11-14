# No credentials here: the AWS provider uses the default credential chain
# (AWS_PROFILE / env vars / SSO / instance role).
provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

# Helm talks to the new cluster using a short-lived token from `aws eks get-token`
# (requires the AWS CLI on the machine running Terraform).
provider "helm" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}

data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  name = var.cluster_name
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)

  tags = {
    Project   = "eks-llm-lab"
    ManagedBy = "terraform"
    Owner     = var.owner
  }
}
