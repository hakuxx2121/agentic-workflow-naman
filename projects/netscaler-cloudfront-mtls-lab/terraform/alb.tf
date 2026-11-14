# ------------------------------------------------------------------
# Option 2: Appian goes to an ALB doing mTLS VERIFY with a trust store + CRL.
# This is the closest AWS-native equivalent of "NetScaler terminates the CAC".
# ------------------------------------------------------------------

# The lab server cert (issued by our fake CA) imported into ACM. ACM accepts
# imported certs from private CAs; browsers won't trust it, curl --cacert will.
resource "aws_acm_certificate" "lab_server" {
  private_key       = file("${var.pki_dir}/server.key")
  certificate_body  = file("${var.pki_dir}/server.pem")
  certificate_chain = file("${var.pki_dir}/ca-bundle.pem")
}

resource "aws_lb_trust_store" "this" {
  name                                     = "${var.name}-ts"
  ca_certificates_bundle_s3_bucket         = aws_s3_bucket.pki.id
  ca_certificates_bundle_s3_key            = aws_s3_object.ca_bundle.key
  ca_certificates_bundle_s3_object_version = aws_s3_object.ca_bundle.version_id
}

# Revocation list. Re-run make-pki + apply to push a new CRL (new object version).
resource "aws_lb_trust_store_revocation" "crl" {
  count                         = var.enable_crl ? 1 : 0
  trust_store_arn               = aws_lb_trust_store.this.arn
  revocations_s3_bucket         = aws_s3_bucket.pki.id
  revocations_s3_key            = aws_s3_object.crl.key
  revocations_s3_object_version = aws_s3_object.crl.version_id
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-alb-"
  vpc_id      = aws_vpc.this.id
  description = "mTLS listener from allowed clients"

  ingress {
    description = "mTLS (Appian path)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.allowed_client_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Separate SG for the CloudFront-only origin listener: only CloudFront edge IPs.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb_from_cloudfront" {
  name_prefix = "${var.name}-alb-cf-"
  vpc_id      = aws_vpc.this.id
  description = "Port 80 origin listener, CloudFront only"

  ingress {
    description     = "CloudFront origin-facing"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }
}

resource "aws_lb" "this" {
  name               = "${var.name}-alb"
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id, aws_security_group.alb_from_cloudfront.id]
  # Strip any client-sent X-Amzn-Mtls-* style junk is automatic for ALB-owned headers;
  # also drop malformed headers:
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "appian" {
  name     = "${var.name}-appian"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = aws_vpc.this.id

  health_check {
    path    = "/healthz"
    matcher = "200"
  }
}

resource "aws_lb_target_group_attachment" "appian" {
  target_group_arn = aws_lb_target_group.appian.arn
  target_id        = aws_instance.backend.id
  port             = 8080
}

# 443: Appian path. mutual_authentication mode = "verify" (try "passthrough" to compare).
resource "aws_lb_listener" "mtls" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.lab_server.arn

  mutual_authentication {
    mode                             = "verify"
    trust_store_arn                  = aws_lb_trust_store.this.arn
    ignore_client_certificate_expiry = false
    advertise_trust_store_ca_names   = "on"
  }

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.appian.arn
  }

  depends_on = [aws_lb_trust_store_revocation.crl]
}

# 80: plain origin for CloudFront ("everything else" path). LAB SHORTCUT:
# production should use HTTPS to the origin + a secret origin header or VPC origin.
resource "aws_lb_listener" "cf_origin" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      status_code  = "200"
      message_body = "other-apps origin: served via CloudFront without client certs\n"
    }
  }
}

# Option 1 experiment: requests arriving from the mTLS CloudFront distribution carry
# CloudFront-Viewer-Cert-* headers -> send them to the echo app so you can see them.
# (The plain "other apps" distribution doesn't forward viewer headers, and port 80 only
# accepts CloudFront IPs. Production would add a secret origin header check too.)
resource "aws_lb_listener_rule" "cf_mtls_to_appian" {
  count        = var.enable_cloudfront_mtls ? 1 : 0
  listener_arn = aws_lb_listener.cf_origin.arn
  priority     = 10

  condition {
    http_header {
      http_header_name = "CloudFront-Viewer-Cert-Present"
      values           = ["1"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.appian.arn
  }
}
