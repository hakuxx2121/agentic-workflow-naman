module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.29"

  name               = local.name
  kubernetes_version = var.kubernetes_version

  # Public API endpoint so you can run kubectl from your laptop. Lock down with
  # endpoint_public_access_cidrs = ["<your-ip>/32"] if you like.
  endpoint_public_access = true

  # The identity running Terraform becomes cluster admin (needed to install Helm charts).
  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns                = {}
    eks-pod-identity-agent = { before_compute = true } # lets Karpenter get AWS creds without static keys
    kube-proxy             = {}
    vpc-cni                = { before_compute = true }
  }

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.intra_subnets

  # Small, always-on node group for "system" pods. Everything else is Karpenter's job.
  eks_managed_node_groups = {
    system = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.system_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = 2
      max_size     = 3
      desired_size = 2

      labels = {
        "karpenter.sh/controller" = "true"
        "node-role/system"        = "true"
      }
    }
  }

  # Karpenter-launched nodes reuse this security group (found via tag).
  node_security_group_tags = {
    "karpenter.sh/discovery" = local.name
  }
}
