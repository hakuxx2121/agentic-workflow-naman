# Route 53: Terraform manages records (and optionally the zone). It does NOT register the domain;
# registering costs money and is done once, by hand (README step 2), after Naman approves.

resource "aws_route53_zone" "this" {
  count = var.existing_hosted_zone_id == "" ? 1 : 0
  name  = var.domain_name
}

data "aws_route53_zone" "existing" {
  count   = var.existing_hosted_zone_id == "" ? 0 : 1
  zone_id = var.existing_hosted_zone_id
}

locals {
  zone_id = var.existing_hosted_zone_id == "" ? aws_route53_zone.this[0].zone_id : data.aws_route53_zone.existing[0].zone_id
}

# ---------- ACM certificate (free) with DNS validation ----------
resource "aws_acm_certificate" "site" {
  domain_name       = var.site_hostname
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.site.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id         = local.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# ---------- Alias records -> ALB (alias queries to AWS resources are free) ----------
resource "aws_route53_record" "site_a" {
  zone_id = local.zone_id
  name    = var.site_hostname
  type    = "A"
  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "site_aaaa" {
  count   = var.enable_ipv6 ? 1 : 0
  zone_id = local.zone_id
  name    = var.site_hostname
  type    = "AAAA"
  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
