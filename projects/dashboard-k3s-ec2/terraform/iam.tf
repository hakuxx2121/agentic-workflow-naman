# Two identities, each scoped to ONE bucket and ONE prefix:
#   1. node role       -> read-only (the S3 sync sidecar pulls the site + data)
#   2. publisher user  -> write (Graph Bot's nightly push). Terraform creates NO access key for it.

locals {
  bucket_arn  = aws_s3_bucket.data.arn
  prefix_glob = "${var.data_prefix}*"
}

# ---------- 1. Node role (EC2 instance profile) ----------
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${local.name}-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# Lets you open a shell / port-forward with SSM Session Manager instead of SSH.
resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "node_read" {
  statement {
    sid       = "ListOnlyThePrefix"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [var.data_prefix, local.prefix_glob]
    }
  }
  statement {
    sid       = "ReadObjects"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/${local.prefix_glob}"]
  }
}

resource "aws_iam_role_policy" "node_read" {
  name   = "dashboard-bucket-read"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.node_read.json
}

resource "aws_iam_instance_profile" "node" {
  name = "${local.name}-node"
  role = aws_iam_role.node.name
}

# ---------- 2. Publisher (nightly scorer) ----------
# An IAM user because Graph Bot runs outside AWS. Create its access key BY HAND (README step 9),
# store it only in a local AWS profile named `dashboard-publisher`, and delete it at teardown.
resource "aws_iam_user" "publisher" {
  name = "${local.name}-publisher"
  path = "/dashboard/"
}

data "aws_iam_policy_document" "publisher" {
  statement {
    sid       = "ListOnlyThePrefix"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [var.data_prefix, local.prefix_glob]
    }
  }
  statement {
    sid       = "WriteObjects"
    actions   = var.publisher_allow_delete ? ["s3:PutObject", "s3:DeleteObject"] : ["s3:PutObject"]
    resources = ["${local.bucket_arn}/${local.prefix_glob}"]
  }
}

resource "aws_iam_user_policy" "publisher" {
  name   = "dashboard-bucket-write"
  user   = aws_iam_user.publisher.name
  policy = data.aws_iam_policy_document.publisher.json
}
