locals {
  fqdn_mtls   = "${var.mtls_host}.${var.domain}"
  fqdn_public = "${var.public_host}.${var.domain}"
  fqdn_origin = "${var.origin_host}.${var.domain}"
}

data "aws_route53_zone" "this" {
  name         = var.domain
  private_zone = false
}

# ---------------- Phase 1: cert, PKI in S3, trust store + CRL, origin secret ----------------
resource "aws_acm_certificate" "wildcard" {
  domain_name               = "*.${var.domain}"
  subject_alternative_names = [var.domain]
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "acm_validation" {
  for_each        = { for o in aws_acm_certificate.wildcard.domain_validation_options : o.domain_name => o }
  zone_id         = data.aws_route53_zone.this.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "wildcard" {
  certificate_arn         = aws_acm_certificate.wildcard.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}

resource "aws_s3_bucket" "pki" {
  bucket_prefix = "mtls-lab-pki-"
  force_destroy = true
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
  bucket     = aws_s3_bucket.pki.id
  key        = "trust/ca-bundle.pem"
  source     = "${var.pki_dir}/ca-bundle.pem"
  etag       = filemd5("${var.pki_dir}/ca-bundle.pem")
  depends_on = [aws_s3_bucket_versioning.pki]
}

resource "aws_s3_object" "crl" {
  bucket     = aws_s3_bucket.pki.id
  key        = "crl/int-ca.crl.pem"
  source     = "${var.pki_dir}/int-ca.crl.pem"
  etag       = filemd5("${var.pki_dir}/int-ca.crl.pem")
  depends_on = [aws_s3_bucket_versioning.pki]
}

resource "aws_lb_trust_store" "this" {
  name                                     = "mtls-lab-ts"
  ca_certificates_bundle_s3_bucket         = aws_s3_bucket.pki.id
  ca_certificates_bundle_s3_key            = aws_s3_object.ca_bundle.key
  ca_certificates_bundle_s3_object_version = aws_s3_object.ca_bundle.version_id
}

resource "aws_lb_trust_store_revocation" "crl" {
  trust_store_arn               = aws_lb_trust_store.this.arn
  revocations_s3_bucket         = aws_s3_bucket.pki.id
  revocations_s3_key            = aws_s3_object.crl.key
  revocations_s3_object_version = aws_s3_object.crl.version_id
}

resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# ---------------- Phase 2 (alb_ready = true): find the ALB, CloudFront, DNS ----------------
# The AWS Load Balancer Controller tags an explicit IngressGroup's ALB with ingress.k8s.aws/stack = <group>.
data "aws_lb" "group" {
  count = var.alb_ready ? 1 : 0
  tags  = { "ingress.k8s.aws/stack" = var.alb_group_name }
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader" # Host = origin hostname, so the ALB host rule matches
}

resource "aws_cloudfront_distribution" "public" {
  count           = var.alb_ready ? 1 : 0
  enabled         = true
  comment         = "mtls-lab non-mTLS apps"
  aliases         = [local.fqdn_public]
  price_class     = "PriceClass_100"
  is_ipv6_enabled = true
  http_version    = "http2and3"

  origin {
    origin_id   = "alb-8443"
    domain_name = local.fqdn_origin # must match the ALB cert (wildcard) for HTTPS to origin
    custom_origin_config {
      http_port              = 80
      https_port             = 8443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }
  }

  default_cache_behavior {
    target_origin_id         = "alb-8443"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.wildcard.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  depends_on = [aws_route53_record.origin]
}

# appian.<domain> -> ALB directly (Option 2: the mTLS host BYPASSES CloudFront)
resource "aws_route53_record" "mtls" {
  count   = var.alb_ready ? 1 : 0
  zone_id = data.aws_route53_zone.this.zone_id
  name    = local.fqdn_mtls
  type    = "A"
  alias {
    name                   = data.aws_lb.group[0].dns_name
    zone_id                = data.aws_lb.group[0].zone_id
    evaluate_target_health = false
  }
}

# origin.<domain> -> same ALB (only CloudFront IPs can reach :8443)
resource "aws_route53_record" "origin" {
  count   = var.alb_ready ? 1 : 0
  zone_id = data.aws_route53_zone.this.zone_id
  name    = local.fqdn_origin
  type    = "A"
  alias {
    name                   = data.aws_lb.group[0].dns_name
    zone_id                = data.aws_lb.group[0].zone_id
    evaluate_target_health = false
  }
}

# app.<domain> -> CloudFront
resource "aws_route53_record" "public" {
  for_each = var.alb_ready ? toset(["A", "AAAA"]) : toset([])
  zone_id  = data.aws_route53_zone.this.zone_id
  name     = local.fqdn_public
  type     = each.key
  alias {
    name                   = aws_cloudfront_distribution.public[0].domain_name
    zone_id                = aws_cloudfront_distribution.public[0].hosted_zone_id
    evaluate_target_health = false
  }
}
