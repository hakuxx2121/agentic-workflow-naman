output "alb_dns_name" {
  description = "Appian path (Option 2). Test with: tests/run-tests.sh aws"
  value       = aws_lb.this.dns_name
}

output "cloudfront_other_apps_url" {
  description = "Everything-else path, no client cert needed."
  value       = "https://${aws_cloudfront_distribution.other_apps.domain_name}/"
}

output "cloudfront_mtls_host" {
  description = "Option 1 experiment host (only if enable_cloudfront_mtls = true)."
  value       = var.enable_cloudfront_mtls ? (var.cloudfront_mtls_alias != "" ? var.cloudfront_mtls_alias : aws_cloudfront_distribution.appian_mtls[0].domain_name) : null
}

output "trust_store_arn" {
  value = aws_lb_trust_store.this.arn
}

output "pki_bucket" {
  value = aws_s3_bucket.pki.id
}

output "account_id" {
  description = "Double-check this is your LAB account before you apply anything else."
  value       = data.aws_caller_identity.current.account_id
}

output "teardown" {
  value = "terraform destroy   (then delete the mtls-lab IAM access key)"
}
