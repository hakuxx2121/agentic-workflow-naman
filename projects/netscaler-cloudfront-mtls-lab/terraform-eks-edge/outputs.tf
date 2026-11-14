output "certificate_arn" { value = aws_acm_certificate_validation.wildcard.certificate_arn }
output "trust_store_arn" { value = aws_lb_trust_store.this.arn }
output "cloudfront_prefix_list_id" { value = data.aws_ec2_managed_prefix_list.cloudfront.id }
output "pki_bucket" { value = aws_s3_bucket.pki.id }
output "mtls_host" { value = local.fqdn_mtls }
output "public_host" { value = local.fqdn_public }
output "origin_host" { value = local.fqdn_origin }

output "origin_verify_secret" {
  value     = random_password.origin_verify.result
  sensitive = true # terraform output -raw origin_verify_secret
}

output "alb_dns_name" { value = var.alb_ready ? data.aws_lb.group[0].dns_name : null }
output "cloudfront_domain" { value = var.alb_ready ? aws_cloudfront_distribution.public[0].domain_name : null }
