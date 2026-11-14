# IAM role for the Karpenter controller (via EKS Pod Identity), IAM role for the
# nodes it launches, and an SQS queue + EventBridge rules for spot interruption notices.
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 21.29"

  cluster_name = module.eks.cluster_name

  node_iam_role_use_name_prefix   = false
  node_iam_role_name              = "${local.name}-karpenter-node" # referenced by the EC2NodeClass
  create_pod_identity_association = true

  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}

resource "helm_release" "karpenter" {
  namespace  = "kube-system"
  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_version
  wait       = true

  values = [yamlencode({
    nodeSelector = { "karpenter.sh/controller" = "true" }
    dnsPolicy    = "Default"
    replicas     = 1 # one replica is enough for a lab
    settings = {
      clusterName       = module.eks.cluster_name
      clusterEndpoint   = module.eks.cluster_endpoint
      interruptionQueue = module.karpenter.queue_name
    }
    webhook = { enabled = false }
  })]
}

# NodePools + EC2NodeClass, shipped as a tiny local Helm chart so Terraform can
# install them right after the Karpenter CRDs exist (no kubectl provider needed).
resource "helm_release" "karpenter_nodepools" {
  name      = "karpenter-nodepools"
  namespace = "kube-system"
  chart     = "${path.module}/charts/karpenter-nodepools"

  values = [yamlencode({
    clusterName  = module.eks.cluster_name
    nodeRoleName = module.karpenter.node_iam_role_name
    cpu = {
      cpuLimit = var.cpu_nodepool_cpu_limit
    }
    gpu = {
      enabled = var.enable_gpu_nodepool
    }
  })]

  depends_on = [helm_release.karpenter]
}
