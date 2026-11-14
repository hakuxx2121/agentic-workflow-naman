locals {
  tags = {
    Project   = var.name
    ManagedBy = "terraform"
    Purpose   = "learning-lab-delete-me"
  }
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# ------------------------------------------------------------------
# Network: tiny VPC, 2 public subnets (ALB needs 2 AZs). No NAT gateway
# (that alone would be ~$1/day) - the backend gets a public IP for its
# one-time package-free boot, and its SG only admits the ALB.
# ------------------------------------------------------------------
resource "aws_vpc" "this" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(aws_vpc.this.cidr_block, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ------------------------------------------------------------------
# S3: holds the CA bundle (trust store) and the CRL. Private, encrypted.
# ------------------------------------------------------------------
resource "aws_s3_bucket" "pki" {
  bucket_prefix = "${var.name}-pki-"
  force_destroy = true # lab only: lets `terraform destroy` empty it
}

resource "aws_s3_bucket_public_access_block" "pki" {
  bucket                  = aws_s3_bucket.pki.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "pki" {
  bucket = aws_s3_bucket.pki.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_object" "ca_bundle" {
  bucket = aws_s3_bucket.pki.id
  key    = "trust/ca-bundle.pem"
  source = "${var.pki_dir}/ca-bundle.pem"
  etag   = filemd5("${var.pki_dir}/ca-bundle.pem")
}

resource "aws_s3_object" "crl" {
  bucket = aws_s3_bucket.pki.id
  key    = "crl/int-ca.crl.pem"
  source = "${var.pki_dir}/int-ca.crl.pem"
  etag   = filemd5("${var.pki_dir}/int-ca.crl.pem")
}
