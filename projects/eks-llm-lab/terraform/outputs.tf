output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "configure_kubectl" {
  description = "Run this to point kubectl at the new cluster."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "karpenter_interruption_queue" {
  value = module.karpenter.queue_name
}

output "vpc_id" {
  description = "Needed by the AWS Load Balancer Controller Helm values (gitops/apps/values.yaml)."
  value       = module.vpc.vpc_id
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_lb_controller_role_arn" {
  value = var.enable_aws_lb_controller ? aws_iam_role.aws_lb_controller[0].arn : null
}
