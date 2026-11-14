# ------------------------------------------------------------------
# The mock "Appian": one t4g.nano running the stdlib-only Python echo app.
# Amazon Linux 2023 ships python3, so nothing is downloaded at boot.
# ------------------------------------------------------------------
data "aws_ssm_parameter" "al2023_arm" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_security_group" "backend" {
  name_prefix = "${var.name}-backend-"
  vpc_id      = aws_vpc.this.id
  description = "Only the ALB may talk to the app (identity headers must not be forgeable)"

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "backend" {
  ami                    = data.aws_ssm_parameter.al2023_arm.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.backend.id]

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  user_data_replace_on_change = true
  user_data                   = <<-EOT
    #!/bin/bash
    set -e
    mkdir -p /opt/mock-appian
    echo "${base64encode(file("${path.module}/../local/backend/app.py"))}" | base64 -d > /opt/mock-appian/app.py
    cat > /etc/systemd/system/mock-appian.service <<'UNIT'
    [Unit]
    Description=mock appian
    After=network-online.target
    [Service]
    Environment=IDENTITY_FIELD=${var.identity_field}
    Environment=PORT=8080
    ExecStart=/usr/bin/python3 /opt/mock-appian/app.py
    DynamicUser=yes
    Restart=always
    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now mock-appian
  EOT

  tags = { Name = "${var.name}-mock-appian" }
}
