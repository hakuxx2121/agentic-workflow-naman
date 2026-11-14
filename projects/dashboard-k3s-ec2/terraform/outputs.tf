output "site_url" {
  description = "Public URL of the dashboard."
  value       = "https://${var.site_hostname}/"
}

output "instance_id" {
  description = "k3s node ID. Use with: aws ssm start-session --target <id>"
  value       = aws_instance.k3s.id
}

output "bucket_name" {
  description = "S3 bucket for the published site + data. Put this in the Argo CD Application (sync.bucket) and push-data.sh --bucket."
  value       = aws_s3_bucket.data.bucket
}

output "data_prefix" {
  description = "Prefix inside the bucket the pod syncs."
  value       = var.data_prefix
}

output "publisher_user_name" {
  description = "IAM user for the nightly push. Create its access key by hand (README step 9)."
  value       = aws_iam_user.publisher.name
}

output "node_port" {
  description = "NodePort the Helm chart must use (service.nodePort)."
  value       = var.node_port
}

output "alb_dns_name" {
  description = "ALB hostname (the Route 53 alias points here)."
  value       = aws_lb.this.dns_name
}

output "hosted_zone_id" {
  description = "Route 53 zone holding the records."
  value       = local.zone_id
}

output "hosted_zone_name_servers" {
  description = "Only set when Terraform created the zone: point your domain's NS records at these."
  value       = var.existing_hosted_zone_id == "" ? aws_route53_zone.this[0].name_servers : []
}

output "vpc_cidr" {
  description = "Use as networkPolicy.vpcCidr in the chart values."
  value       = var.vpc_cidr
}

output "waf_enabled" {
  value = var.enable_waf
}
