variable "region" {
  description = "Region for the ALB, EC2 and S3 bucket."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name prefix for every resource."
  type        = string
  default     = "mtls-lab"
}

variable "lab_domain" {
  description = "FAKE hostname baked into the lab server cert (must match LAB_DOMAIN used by scripts/make-pki.sh). You never need DNS for it; tests use curl --connect-to."
  type        = string
  default     = "appian.lab.example.com"
}

variable "pki_dir" {
  description = "Where scripts/make-pki.sh wrote the lab PKI."
  type        = string
  default     = "../pki"
}

variable "allowed_client_cidrs" {
  description = "Who may reach the ALB's mTLS listener. Set to [\"<your-public-ip>/32\"]."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "identity_field" {
  description = "Which cert field the mock Appian maps to a user: subject | serial | dn | upn."
  type        = string
  default     = "subject"
}

variable "instance_type" {
  description = "Backend instance. t4g.nano is the cheapest Graviton size."
  type        = string
  default     = "t4g.nano"
}

variable "enable_crl" {
  description = "Attach the issuing CA's CRL to the ALB trust store (turn off to watch the revoked cert get IN)."
  type        = bool
  default     = true
}

# ---- Option 1 experiment: CloudFront viewer mTLS (off by default) ----
variable "enable_cloudfront_mtls" {
  description = "Create a SECOND CloudFront distribution with viewer mTLS (required mode) in front of the ALB's plain path."
  type        = bool
  default     = false
}

variable "cloudfront_mtls_alias" {
  description = "Optional real hostname you own for the mTLS distribution (leave empty to use the *.cloudfront.net name)."
  type        = string
  default     = ""
}

variable "cloudfront_mtls_acm_cert_arn" {
  description = "Public ACM cert in us-east-1 covering cloudfront_mtls_alias. Required only if alias is set."
  type        = string
  default     = ""
}
