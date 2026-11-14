# ------------------------------------------------------------------
# AWS Load Balancer Controller: IAM only. The controller itself is installed by
# Argo CD (gitops/apps/templates/aws-load-balancer-controller.yaml), the same way
# everything else in this lab is. Uses EKS Pod Identity (like Karpenter here),
# so there is no OIDC/IRSA setup to do.
# Policy = official iam_policy.json for controller v3.6.2 (vendored in policies/).
# ------------------------------------------------------------------
resource "aws_iam_policy" "aws_lb_controller" {
  count  = var.enable_aws_lb_controller ? 1 : 0
  name   = "${local.name}-aws-lb-controller"
  policy = file("${path.module}/policies/aws-lb-controller-iam-policy.json")
}

resource "aws_iam_role" "aws_lb_controller" {
  count = var.enable_aws_lb_controller ? 1 : 0
  name  = "${local.name}-aws-lb-controller"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "aws_lb_controller" {
  count      = var.enable_aws_lb_controller ? 1 : 0
  role       = aws_iam_role.aws_lb_controller[0].name
  policy_arn = aws_iam_policy.aws_lb_controller[0].arn
}

# Binds the role to the kube-system/aws-load-balancer-controller ServiceAccount
# that the Helm chart creates (name pinned in the Argo CD Application).
resource "aws_eks_pod_identity_association" "aws_lb_controller" {
  count           = var.enable_aws_lb_controller ? 1 : 0
  cluster_name    = module.eks.cluster_name
  namespace       = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn        = aws_iam_role.aws_lb_controller[0].arn
}
data "aws_caller_identity" "current" {}
