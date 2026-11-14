variable "region" {
  type    = string
  default = "us-east-1"
  validation {
    condition     = var.region == "us-east-1"
    error_message = "Keep us-east-1: the one wildcard ACM cert is shared by the ALB and CloudFront."
  }
}

variable "domain" {
  description = "Route 53 public hosted zone you own, e.g. example.com (placeholder)."
  type        = string
}

variable "mtls_host" {
  description = "Option 2 host: straight to the ALB, mTLS verify."
  type        = string
  default     = "appian"
}

variable "public_host" {
  description = "Non-mTLS host served through CloudFront."
  type        = string
  default     = "app"
}

variable "origin_host" {
  description = "Hostname CloudFront uses to reach the ALB (:8443)."
  type        = string
  default     = "origin"
}

variable "pki_dir" {
  type    = string
  default = "../pki"
}

variable "alb_group_name" {
  description = "alb.ingress.kubernetes.io/group.name used by the mtls-echo Ingresses."
  type        = string
  default     = "mtls-lab"
}

variable "alb_ready" {
  description = "Phase 2 switch. Set true AFTER Argo CD has created the ALB: adds CloudFront + DNS records."
  type        = bool
  default     = false
}
