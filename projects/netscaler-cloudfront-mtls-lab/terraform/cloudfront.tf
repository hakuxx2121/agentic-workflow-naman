# ------------------------------------------------------------------
# "Everything else" path: a normal CloudFront distribution, no client certs.
# PriceClass_100 = cheapest (US/Canada/Europe edges).
# ------------------------------------------------------------------
data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "other_apps" {
  enabled         = true
  comment         = "${var.name} other apps (no mTLS)"
  price_class     = "PriceClass_100"
  is_ipv6_enabled = true
  http_version    = "http2"

  origin {
    origin_id   = "alb-plain"
    domain_name = aws_lb.this.dns_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # lab shortcut, see alb.tf
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "alb-plain"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.disabled.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# ------------------------------------------------------------------
# Option 1 experiment (enable_cloudfront_mtls = true):
# CloudFront viewer mTLS, REQUIRED mode, trust store from the same S3 bundle.
# CloudFront forwards CloudFront-Viewer-Cert-* headers to the origin via an
# origin request policy. Origin is the ALB's port-80 listener; a listener rule
# (alb.tf) forwards requests carrying CloudFront-Viewer-Cert-Present=1 to the echo app.
# Revocation: CloudFront has NO CRL upload; it offers OCSP (needs a reachable
# responder URL in the cert - our lab certs have none) or a connection function
# + KeyValueStore deny-list. So the revoked-cert test is EXPECTED to pass through here.
# ------------------------------------------------------------------
resource "aws_cloudfront_trust_store" "this" {
  count = var.enable_cloudfront_mtls ? 1 : 0
  name  = "${var.name}-cf-ts"

  ca_certificates_bundle_source {
    ca_certificates_bundle_s3_location {
      bucket = aws_s3_bucket.pki.id
      key    = aws_s3_object.ca_bundle.key
      region = var.region
    }
  }
}

resource "aws_cloudfront_origin_request_policy" "viewer_cert" {
  count   = var.enable_cloudfront_mtls ? 1 : 0
  name    = "${var.name}-viewer-cert-headers"
  comment = "Forward client cert details to origin"

  cookies_config { cookie_behavior = "none" }
  query_strings_config { query_string_behavior = "all" }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = [
        "CloudFront-Viewer-Cert-Serial-Number",
        "CloudFront-Viewer-Cert-Issuer",
        "CloudFront-Viewer-Cert-Subject",
        "CloudFront-Viewer-Cert-Present",
        "CloudFront-Viewer-Cert-Sha256",
        "CloudFront-Viewer-Cert-Validity",
        "CloudFront-Viewer-Cert-Pem",
      ]
    }
  }
}

resource "aws_cloudfront_distribution" "appian_mtls" {
  count           = var.enable_cloudfront_mtls ? 1 : 0
  enabled         = true
  comment         = "${var.name} Option 1: viewer mTLS at the edge"
  price_class     = "PriceClass_100"
  is_ipv6_enabled = true
  http_version    = "http2" # viewer mTLS is not supported on HTTP/3
  aliases         = var.cloudfront_mtls_alias == "" ? [] : [var.cloudfront_mtls_alias]

  origin {
    origin_id   = "alb-plain"
    domain_name = aws_lb.this.dns_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id         = "alb-plain"
    viewer_protocol_policy   = "https-only" # mTLS requires HTTPS-only behaviors
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.viewer_cert[0].id
  }

  viewer_mtls_config {
    mode = "required"
    trust_store_config {
      trust_store_id                 = aws_cloudfront_trust_store.this[0].id
      advertise_trust_store_ca_names = true
      ignore_certificate_expiry      = false
    }
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.cloudfront_mtls_alias == ""
    acm_certificate_arn            = var.cloudfront_mtls_alias == "" ? null : var.cloudfront_mtls_acm_cert_arn
    ssl_support_method             = var.cloudfront_mtls_alias == "" ? null : "sni-only"
    minimum_protocol_version       = var.cloudfront_mtls_alias == "" ? null : "TLSv1.2_2021"
  }
}
