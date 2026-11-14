# Creator dashboard on k3s (AWS EC2)

Terraform, Helm, and optional Argo CD to host the **Creator Calls** static dashboard on a single **k3s** node in AWS. Traffic lands on an Application Load Balancer with an ACM certificate and a Route 53 alias. Site files and JSON data live in S3; a sidecar in the pod syncs them on a timer using the instance role (no access keys in the cluster).

Built with the **Tech Bot** Grok Bot agent under Naman's direction.

The `docs/` and `argocd/` folders were empty when this copy was staged. Argo CD itself can be installed at first boot by k3s's built-in Helm controller (`install_argocd = true` in Terraform). Application manifests for the dashboard chart are not in `argocd/` yet; you can install the chart with Helm directly.

## What Terraform creates

- A VPC and public subnets in two Availability Zones (the ALB needs two; the k3s node sits in the first). Default CIDR is `10.60.0.0/16`, chosen so it does not overlap k3s pod (`10.42.0.0/16`) or service (`10.43.0.0/16`) ranges. IPv6 / dual-stack ALB is on by default.
- One EC2 instance (`t4g.small` by default, ARM, encrypted gp3 root volume, CPU credits set to `standard`). IMDSv2 is required. You connect with SSM, not a public SSH key in this repo.
- User data installs **k3s** as a single-node server, with Traefik and ServiceLB disabled (the ALB is the front door; the app is a NodePort). Kubernetes Secrets are encrypted at rest in k3s's datastore.
- If `install_argocd` is true, user data also writes a k3s `HelmChart` manifest for a trimmed Argo CD (Dex and notifications off, tight memory requests/limits). The Argo CD server is set insecure because it is meant to be reached only through an SSM port-forward, not exposed publicly.
- An internet-facing ALB, ACM certificate with DNS validation, and Route 53 alias records (A and, when IPv6 is on, AAAA) for `site_hostname`.
- An S3 bucket for the published site and data, with versioning and a lifecycle rule that expires noncurrent versions. An IAM user (`publisher`) is created for the nightly upload; you create its access key yourself. The node instance profile can read the bucket prefix; the publisher user can upload (and optionally delete) objects under that prefix.
- Optional AWS WAF on the ALB (rate limit + managed common rule set). Off by default because of the extra monthly cost.

No AWS access keys or account numbers are stored in this repo. The provider uses your local credential chain (`AWS_PROFILE`). State is local by default and should stay gitignored.

## Helm chart (`charts/creator-dashboard`)

- Unprivileged nginx (`nginxinc/nginx-unprivileged`) serves the static site from a shared volume.
- An init container and a sidecar run `files/sync.sh` with the AWS CLI image, copying `s3://$BUCKET/$PREFIX` into the volume (initial sync, then on `intervalSeconds`, default 10 minutes).
- A ClusterIP/NodePort Service on port **30080** (must match `var.node_port` / the ALB target group). `externalTrafficPolicy: Local` keeps client source IPs.
- A NetworkPolicy (k3s kube-router) allows ingress from the VPC CIDR, DNS egress, HTTPS to S3, and IMDSv2 (`169.254.169.254`).
- Pod hardening: non-root, read-only root filesystem, dropped capabilities, RuntimeDefault seccomp, no automounted service account token.

`scripts/push-data.sh` uploads data (and optionally the site) to the bucket. By default it **strips the "My holdings" ticker list** from the public `config.js` / `v2.js` and hides the holdings button, then `scripts/audit-public.sh` can scan the staged tree for keys, tokens, and leftover holdings lists. `scripts/push_data.py` is a boto3-only path for the four data JSON files.

## Tech stack

- Terraform >= 1.6, AWS provider ~> 6.70
- Amazon Linux / k3s on EC2 (ARM), AWS ALB, ACM, Route 53, S3, IAM, optional WAF
- Helm chart for the dashboard; optional Argo CD via the k3s Helm controller
- Bash / Python 3 publish and audit scripts

## How to run

1. Use a personal or sandbox AWS account. Create a profile (for example `dashboard-admin`) with rights to build the stack, and later a `dashboard-publisher` profile for uploads only.
2. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` and set `domain_name`, `site_hostname`, and (if you already registered the domain in Route 53) `existing_hosted_zone_id`.
3. From `terraform/`:

```bash
terraform init
terraform test          # offline plan test in terraform/tests
terraform plan
terraform apply
```

4. After the node is Ready, install or sync the Helm chart with `sync.bucket` set to `terraform output -raw bucket_name`, `networkPolicy.vpcCidr` set to the VPC CIDR output, and `service.nodePort` equal to `node_port` (30080 by default).
5. Publish files:

```bash
# from this folder; default source is the sibling creator-calls-dashboard project
./scripts/push-data.sh --bucket "$(terraform -chdir=terraform output -raw bucket_name)" --with-site
```

6. Tear down with `terraform destroy`. Flip `bucket_force_destroy` to true and apply first if the bucket still has objects.

An offline end-to-end test of push → fake S3 → sync.sh → nginx (no AWS, no cluster) is `tests/e2e-local.sh`. It needs `python3`, `curl`, `helm`, and an nginx binary.

## What is not in this copy

- `.terraform/` provider plugins and any `terraform.tfstate` (state can hold resource IDs and ARNs; it is gitignored)
- Filled-in `terraform.tfvars` and AWS keys


## What was removed and how to run it yourself

**Removed (security):**
- Terraform state (`terraform.tfstate`) and the `.terraform/` provider cache. State can hold resource IDs and ARNs and must stay out of git (already gitignored).
- A filled `terraform.tfvars`. Only `terraform/terraform.tfvars.example` is in the repo (placeholders such as `example.com` and `lab`).
- AWS access keys, account numbers, and any real hosted-zone IDs. Mock ARNs in the offline Terraform test use the documentation account id `123456789012`.
- The `docs/` and `argocd/` Application folders were empty in the working copy; Argo CD is installed at boot via the k3s Helm controller when `install_argocd = true`.

**What you must supply:**

1. An AWS account (personal/sandbox) and a credential profile, for example `dashboard-admin` for apply and `dashboard-publisher` for uploads. The provider uses the default credential chain; no keys are stored in this repo.
2. A domain (or an existing Route 53 public hosted zone). Copy the example vars and edit them:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# set domain_name, site_hostname, and optionally existing_hosted_zone_id
cd terraform && terraform init && terraform test && terraform plan && terraform apply
```

3. After the node is Ready, install the Helm chart with `sync.bucket` set to `terraform output -raw bucket_name`. Publish site/data with:

```bash
./scripts/push-data.sh --bucket "$(terraform -chdir=terraform output -raw bucket_name)" --with-site
```

Create the publisher user's access key yourself and put it in a local AWS profile; do not commit it. Tear down with `terraform destroy` (flip `bucket_force_destroy` first if the bucket still has objects).

An offline check with no AWS account: `tests/e2e-local.sh` (needs python3, curl, helm, and nginx).
