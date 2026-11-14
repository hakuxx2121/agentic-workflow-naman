variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name for the EKS cluster (also used to name the VPC and tag resources for Karpenter discovery)."
  type        = string
  default     = "eks-llm-lab"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version. 1.36 is in EKS standard support (until Aug 2027) as of Oct 2026."
  type        = string
  default     = "1.36"
}

variable "owner" {
  description = "Free-text owner tag put on every resource (helps you find them in the console)."
  type        = string
  default     = "naman"
}

variable "vpc_cidr" {
  description = "CIDR block for the lab VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "system_instance_types" {
  description = "Instance types for the small managed node group that runs system pods (CoreDNS, Karpenter, Argo CD)."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "karpenter_version" {
  description = "Karpenter Helm chart version."
  type        = string
  default     = "1.15.1"
}

variable "argocd_chart_version" {
  description = "argo-cd Helm chart version (argoproj/argo-helm)."
  type        = string
  default     = "10.11.6"
}

variable "enable_gpu_nodepool" {
  description = "Create a Karpenter GPU NodePool (g4dn/g5/g6) and deploy the vLLM GPU variant. Costs real money when a GPU pod is scheduled."
  type        = bool
  default     = false
}

variable "cpu_nodepool_cpu_limit" {
  description = "Safety cap: max total vCPUs Karpenter may launch for the CPU NodePool."
  type        = number
  default     = 16
}

variable "gitops_repo_url" {
  description = "HTTPS URL of YOUR git repo containing this project (e.g. https://github.com/<you>/eks-llm-lab.git). Argo CD reads gitops/ from it."
  type        = string

  validation {
    condition     = can(regex("^(https://|git@)", var.gitops_repo_url))
    error_message = "gitops_repo_url must be an https:// or git@ URL."
  }
}

variable "gitops_revision" {
  description = "Git branch/tag Argo CD should follow."
  type        = string
  default     = "main"
}

variable "enable_aws_lb_controller" {
  description = "Create the IAM role + Pod Identity association for the AWS Load Balancer Controller (mTLS front-door lab)."
  type        = bool
  default     = false
}
