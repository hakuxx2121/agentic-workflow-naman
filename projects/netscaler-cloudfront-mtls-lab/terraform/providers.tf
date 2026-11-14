# No credentials here: the AWS provider uses the default credential chain.
# Run with:  export AWS_PROFILE=mtls-lab
provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}
