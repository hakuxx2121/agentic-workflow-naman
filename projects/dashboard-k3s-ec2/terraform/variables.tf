variable "region" {
  description = "AWS region. us-east-1 is cheapest and keeps the ACM cert, ALB and bucket together."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "creator-dashboard"
}

variable "owner" {
  description = "Owner tag (any label, e.g. your first name). Do not put emails or account numbers here."
  type        = string
  default     = "lab"
}

# ---------- DNS / TLS ----------
variable "domain_name" {
  description = "Apex domain you registered (e.g. example.com). Used only when Terraform creates the hosted zone."
  type        = string
  default     = "example.com"
}

variable "site_hostname" {
  description = "Public hostname for the dashboard (e.g. dash.example.com). Must be inside the hosted zone."
  type        = string
  default     = "dash.example.com"
}

variable "existing_hosted_zone_id" {
  description = <<-EOT
    ID of an existing Route 53 public hosted zone (e.g. Z0123456789ABCDEFGHIJ).
    Registering a domain in Route 53 creates this zone for you, so pass its ID here to avoid a duplicate zone.
    Leave empty ("") to have Terraform create a new zone for var.domain_name (you then point the domain's NS records at it).
  EOT
  type        = string
  default     = ""
}

variable "enable_ipv6" {
  description = "Give the VPC/subnets IPv6 and make the ALB dualstack so an AAAA record can point at it."
  type        = bool
  default     = true
}

# ---------- Network ----------
variable "vpc_cidr" {
  description = "VPC CIDR. Must not overlap k3s defaults (pods 10.42.0.0/16, services 10.43.0.0/16)."
  type        = string
  default     = "10.60.0.0/16"
}

# ---------- EC2 / k3s ----------
variable "instance_type" {
  description = "t4g.small (2 vCPU, 2 GiB, arm64) is enough for k3s + nginx + a trimmed Argo CD. Use t4g.medium if pods get OOM-killed."
  type        = string
  default     = "t4g.small"
}

variable "cpu_credits" {
  description = "\"standard\" = never billed for surplus CPU credits (CPU throttles to 20% baseline if credits run out). \"unlimited\" = can burst but may add $0.04/vCPU-hour."
  type        = string
  default     = "standard"
  validation {
    condition     = contains(["standard", "unlimited"], var.cpu_credits)
    error_message = "cpu_credits must be standard or unlimited."
  }
}

variable "root_volume_gb" {
  description = "Encrypted gp3 root volume size (GiB). k3s images + Argo CD fit in 20."
  type        = number
  default     = 20
}

variable "k3s_version" {
  description = "Pin a k3s release (e.g. v1.37.2+k3s1). Empty = latest on the stable channel at boot time."
  type        = string
  default     = ""
}

variable "install_argocd" {
  description = "Install a trimmed Argo CD (no Dex, no notifications) via k3s's built-in Helm controller at boot."
  type        = bool
  default     = true
}

variable "argocd_chart_version" {
  description = "argo-helm 'argo-cd' chart version."
  type        = string
  default     = "10.18.0"
}

variable "node_port" {
  description = "Fixed NodePort the Helm chart's Service uses. The ALB target group sends traffic here; only the ALB security group may reach it."
  type        = number
  default     = 30080
  validation {
    condition     = var.node_port >= 30000 && var.node_port <= 32767
    error_message = "node_port must be in the Kubernetes NodePort range 30000-32767."
  }
}

# ---------- S3 ----------
variable "data_prefix" {
  description = "Key prefix inside the bucket that holds the published site + data. The pod syncs only this prefix."
  type        = string
  default     = "site/"
}

variable "bucket_force_destroy" {
  description = "Let `terraform destroy` delete a bucket that still has objects/versions. Flip to true (and apply) right before teardown."
  type        = bool
  default     = false
}

variable "noncurrent_version_days" {
  description = "Delete old object versions after this many days (keeps the nightly 10 MB prices.json from piling up)."
  type        = number
  default     = 30
}

variable "publisher_allow_delete" {
  description = "Give the publisher s3:DeleteObject on the prefix. Needed for `aws s3 sync --delete`; versioning makes deletes recoverable."
  type        = bool
  default     = true
}

# ---------- WAF ----------
variable "enable_waf" {
  description = "Attach an AWS WAF web ACL to the ALB (rate limit + AWS managed common rule set). About $7/month + $0.60 per 1M requests."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Max requests per client IP per 5-minute window before WAF blocks it."
  type        = number
  default     = 1000
}
