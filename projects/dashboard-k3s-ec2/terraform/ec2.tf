# Latest Ubuntu 24.04 LTS arm64 AMI, looked up from Canonical's public SSM parameter.
# Ubuntu ships the SSM agent preinstalled, and k3s's installer supports it without SELinux extras.
data "aws_ssm_parameter" "ubuntu_arm64" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
}

resource "aws_instance" "k3s" {
  ami                         = data.aws_ssm_parameter.ubuntu_arm64.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.node.id]
  iam_instance_profile        = aws_iam_instance_profile.node.name
  associate_public_ip_address = true # outbound only (no NAT gateway); the SG blocks all inbound except the ALB

  # No key pair on purpose: you log in with SSM Session Manager, never SSH.

  credit_specification {
    cpu_credits = var.cpu_credits
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required" # IMDSv2 only
    # 2 hops so pods (one network hop behind the node) can fetch the instance role's
    # temporary credentials. That is how the S3 sync sidecar reads the bucket with no keys in the cluster.
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true # AWS-managed EBS key (free)
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    k3s_version          = var.k3s_version
    install_argocd       = var.install_argocd
    argocd_chart_version = var.argocd_chart_version
  })
  # Changing user_data rebuilds the node. Argo CD then redeploys the chart from git (re-apply the Application).
  user_data_replace_on_change = true

  tags = { Name = "${local.name}-k3s" }

  lifecycle {
    # A newer Ubuntu AMI shouldn't replace a running node on every plan. Taint/replace on purpose to upgrade.
    ignore_changes = [ami]
  }
}
