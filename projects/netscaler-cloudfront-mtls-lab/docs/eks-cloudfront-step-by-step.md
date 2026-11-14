# Step by step: CloudFront + ALB mTLS front door on your existing EKS lab

You'll add an **Option 2** front door to the cluster you built from `eks-llm-lab`:

```
 CAC user  --mTLS-->  appian.example.com  --> ALB :443  (verify: trust store + CRL) --> mtls-echo pod
 anyone    --HTTPS--> app.example.com     --> CloudFront --HTTPS + X-Origin-Verify--> origin.example.com
                                                         --> same ALB :8443 (CloudFront IPs only) --> mtls-echo pod
```
There's one ALB (an Ingress **group**) with two listeners. mTLS is configured **per listener port**, so the CloudFront origin
gets its own port (8443) without mTLS. The mTLS host **bypasses CloudFront**.

`example.com` is a placeholder for **your** domain. Every command assumes bash, from your laptop.

**Files this guide uses (already written):**

| Where | File | Purpose |
|---|---|---|
| eks-llm-lab | `terraform/aws-lb-controller.tf`, `terraform/policies/aws-lb-controller-iam-policy.json` | IAM policy (official, controller v3.6.2) + role + **EKS Pod Identity** association (same pattern as Karpenter in this lab) |
| eks-llm-lab | `terraform/variables.tf` (+`enable_aws_lb_controller`), `terraform/outputs.tf` (+`vpc_id`, `account_id`, role ARN) | |
| eks-llm-lab | `gitops/apps/values.yaml` (`mtlsLab:` block, `enabled: false`) | the on/off flag + values |
| eks-llm-lab | `gitops/apps/templates/aws-load-balancer-controller.yaml` | Argo CD app: controller Helm chart 3.6.2 |
| eks-llm-lab | `gitops/apps/templates/mtls-echo.yaml` + `gitops/workloads/mtls-echo/` | Argo CD app: namespace, ConfigMap (app.py), Deployment, Service, 2 Ingresses |
| this lab | `terraform-eks-edge/` | ACM cert, S3 + trust store + CRL, origin secret, then CloudFront + Route 53 records |
| this lab | `tests/run-tests.sh eks <host>` | valid / none / revoked curl tests |

> These eks-llm-lab files were written into the sibling `eks-llm-lab/` folder in this portfolio. If your real repo lives elsewhere,
> copy those paths into it. Argo CD reads **your git repo**, so step 5 only works after you commit and push.

---

## Step 1 - Preflight
**What it does:** confirms you're in the right AWS account and cluster, and sets the shell variables every later step uses.

```bash
export AWS_PROFILE=mtls-lab            # the lab-only access key you created with: aws configure --profile mtls-lab
aws sts get-caller-identity            # check the Account is your SANDBOX account

cd ~/path/to/eks-llm-lab/terraform     # your repo
export REGION=$(terraform output -raw region)
export CLUSTER_NAME=$(terraform output -raw cluster_name)
aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER_NAME"
kubectl config current-context         # ...:cluster/eks-llm-lab
kubectl get nodes

export DOMAIN=example.com              # <- YOUR domain (step 3)
export LAB=~/path/to/netscaler-cloudfront-mtls-lab

# Argo CD UI/CLI (same as the eks-llm-lab README): port-forward + initial admin password
kubectl -n argocd port-forward svc/argocd-server 8080:80 >/dev/null 2>&1 &
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
argocd login localhost:8080 --username admin --insecure --grpc-web   # optional CLI; or open http://localhost:8080
```
`ACCOUNT_ID` and `VPC_ID` come from new outputs, so set them at the end of step 2 after the apply.
**Verify:** `get-caller-identity` shows the sandbox account, `kubectl get nodes` lists nodes, `argocd app list` (or the UI) shows `root`.

---

## Step 2 - AWS Load Balancer Controller (IAM via Terraform, install via Argo CD)
**What it does:** gives the controller AWS permissions through Pod Identity, then has Argo CD install controller **v3.6.2**.
That version supports the `alb.ingress.kubernetes.io/mutual-authentication` annotation.

Annotation syntax, checked against the official docs ([annotations.md](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/main/docs/guide/ingress/annotations.md)):
```yaml
alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS": 443}]'
alb.ingress.kubernetes.io/mutual-authentication: '[{"port": 443, "mode": "verify", "trustStore": "<arn-or-name>", "ignoreClientCertificateExpiry": false, "advertiseTrustStoreCaNames": "on"}]'
```

```bash
cd ~/path/to/eks-llm-lab/terraform
terraform plan  -var enable_aws_lb_controller=true     # expect 4 to add (policy, role, attachment, pod identity association)
terraform apply -var enable_aws_lb_controller=true
# (or put enable_aws_lb_controller = true in terraform.tfvars so later applies don't remove it)
export ACCOUNT_ID=$(terraform output -raw account_id)
export VPC_ID=$(terraform output -raw vpc_id)

# Public subnets: the VPC module ALREADY tags them kubernetes.io/role/elb=1 (vpc.tf). Confirm:
aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID Name=tag:kubernetes.io/role/elb,Values=1 \
  --query 'Subnets[].SubnetId' --output text      # expect 2 subnet IDs
```
Edit `gitops/apps/values.yaml` → `mtlsLab:` and set `clusterName`, `region`, `vpcId` (= `$VPC_ID`). **Leave `enabled: false` for now.** Step 5 turns it on,
after the cert and trust store exist. That way the Ingress never points at a missing ARN.

**Verify:** `aws eks list-pod-identity-associations --cluster-name $CLUSTER_NAME --query 'associations[?serviceAccount==\`aws-load-balancer-controller\`]'` returns one entry.

---

## Step 3 - Domain, Route 53 hosted zone, ACM certificate
**What it does:** gives you a real DNS zone and a publicly trusted wildcard cert (`*.example.com`). The ALB and CloudFront both use it.

If you don't own a domain, buy one in Route 53 (Console → Route 53 → Registered domains; a `.click`/`.link` domain is a few $/year).
That creates the hosted zone for you. If the domain is registered elsewhere:
```bash
aws route53 create-hosted-zone --name "$DOMAIN" --caller-reference "mtls-lab-$(date +%s)"
aws route53 get-hosted-zone --id <ZoneId-from-output> --query 'DelegationSet.NameServers'
# put these 4 name servers at your registrar, then wait:
dig +short NS "$DOMAIN"
```
The ACM cert is created in step 4 by Terraform, together with the trust store, with DNS validation records written automatically.
**Verify:** `dig +short NS $DOMAIN` returns the `awsdns` name servers.

---

## Step 4 - Lab PKI, S3, trust store + CRL, ACM cert, origin secret (Terraform phase 1)
**What it does:** builds the fake CAC-style PKI, uploads the CA bundle and CRL to S3, creates the ALB trust store and attaches the CRL as a revocation list.
It also issues the ACM wildcard cert and generates the CloudFront origin secret.

```bash
cd $LAB
./scripts/make-pki.sh                       # pki/ca-bundle.pem, pki/int-ca.crl.pem, client-valid/revoked certs
cd terraform-eks-edge
cp terraform.tfvars.example terraform.tfvars && sed -i "s/example.com/$DOMAIN/" terraform.tfvars
terraform init
terraform plan                              # ~12 resources, alb_ready=false so no CloudFront yet
terraform apply                             # ACM DNS validation takes ~1-5 min
export CERT_ARN=$(terraform output -raw certificate_arn)
export TRUST_STORE_ARN=$(terraform output -raw trust_store_arn)
export CF_PL=$(terraform output -raw cloudfront_prefix_list_id)
```
CLI equivalent, for learning (don't run it as well as the Terraform):
`aws elbv2 create-trust-store --name mtls-lab-ts --ca-certificates-bundle-s3-bucket <bucket> --ca-certificates-bundle-s3-key trust/ca-bundle.pem`
and then `aws elbv2 add-trust-store-revocations --trust-store-arn <arn> --revocation-contents "S3Bucket=<bucket>,S3Key=crl/int-ca.crl.pem,RevocationType=CRL"`.

**Verify:**
```bash
aws acm describe-certificate --certificate-arn $CERT_ARN --query Certificate.Status        # "ISSUED"
aws elbv2 describe-trust-stores --trust-store-arns $TRUST_STORE_ARN --query 'TrustStores[0].[Status,NumberOfCaCertificates,TotalRevokedEntries]'
# -> ["ACTIVE", 2, 1]
```

---

## Step 5 - Deploy the controller + mock Appian through Argo CD
**What it does:** turns on the `mtlsLab` flag so the root app creates two Argo CD apps: `aws-load-balancer-controller` (sync wave -1) and `mtls-echo`.
The two `mtls-echo` Ingresses make the controller build one ALB.

Fill in `gitops/apps/values.yaml` (print the values first):
```bash
cd $LAB/terraform-eks-edge
echo "vpcId=$VPC_ID certificateArn=$CERT_ARN trustStoreArn=$TRUST_STORE_ARN cloudfrontPrefixListId=$CF_PL"
terraform output -raw origin_verify_secret; echo      # -> originVerifySecret
curl -s https://checkip.amazonaws.com                  # -> mtlsAllowedCidrs: "<that-ip>/32"
```
```yaml
mtlsLab:
  enabled: true
  vpcId: vpc-...
  echo:
    domain: example.com
    mtlsHost: appian.example.com
    originHost: origin.example.com
    certificateArn: arn:aws:acm:us-east-1:...
    trustStoreArn: arn:aws:elasticloadbalancing:us-east-1:...:truststore/mtls-lab-ts/...
    cloudfrontPrefixListId: pl-...
    originVerifySecret: <secret>
    mtlsAllowedCidrs: "<your-ip>/32"
```
> **Lab shortcut, be aware:** `originVerifySecret` ends up in git because ALB rule conditions are plain annotations. Use a **private** repo.
> In production you'd rotate it (Secrets Manager + Lambda) and rely on the prefix list as the main control. Never put AWS keys in this file.

```bash
cd ~/path/to/eks-llm-lab
helm template apps gitops/apps | grep -A3 'name: mtls-echo'            # renders? (local sanity check)
git add gitops terraform && git commit -m "mtls front door lab" && git push
argocd app sync root          # or wait ~3 min for auto-sync
argocd app wait aws-load-balancer-controller mtls-echo --health --timeout 600
```
**Verify:**
```bash
kubectl -n kube-system get deploy aws-load-balancer-controller          # 1/1 READY
kubectl -n mtls-echo get pods,ingress                                    # both Ingresses show the same ADDRESS (k8s-mtlslab-...elb.amazonaws.com)
kubectl -n kube-system logs deploy/aws-load-balancer-controller | grep -i -E 'error|mutual' | tail
export ALB_DNS=$(kubectl -n mtls-echo get ingress mtls-echo-mtls -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
aws elbv2 describe-listeners --load-balancer-arn $(aws elbv2 describe-load-balancers --query "LoadBalancers[?DNSName=='$ALB_DNS'].LoadBalancerArn" --output text) \
  --query 'Listeners[].[Port,MutualAuthentication.Mode]' --output text     # 443 verify / 8443 off
```
If the controller logs `AccessDenied`, check the Pod Identity association from step 2. Then restart the deployment:
`kubectl -n kube-system rollout restart deploy aws-load-balancer-controller`.

---

## Step 6 - CloudFront in front of the ALB for the non-mTLS host (Terraform phase 2)
**What it does:** creates a CloudFront distribution for `app.example.com` that talks **HTTPS** to `origin.example.com:8443` and adds the secret `X-Origin-Verify` header.
The ALB only accepts that port from CloudFront's managed prefix list, and its rule only forwards when the header matches. Anything else gets a 404.
The mTLS host is **not** behind CloudFront.

```bash
cd $LAB/terraform-eks-edge
sed -i 's/alb_ready = false/alb_ready = true/' terraform.tfvars
terraform apply            # finds the ALB by tag ingress.k8s.aws/stack=mtls-lab; CloudFront takes ~5-10 min
```
If the ALB lookup fails, check the tag: `aws elbv2 describe-tags --resource-arns <alb-arn>`.

**Verify:**
```bash
terraform output cloudfront_domain
aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='mtls-lab non-mTLS apps'].Status"   # "Deployed"
curl -s -o /dev/null -w '%{http_code}\n' -k https://$ALB_DNS:8443/public   # from your laptop: times out (SG = CloudFront only)
```

---

## Step 7 - Route 53 alias records
**What it does:** points `appian.example.com` and `origin.example.com` straight at the ALB, and `app.example.com` at CloudFront.
They're already created by the step 6 apply (`aws_route53_record.mtls/origin/public`).

**Verify:**
```bash
dig +short appian.$DOMAIN    # ALB IPs
dig +short app.$DOMAIN       # CloudFront IPs (different from above)
```
CLI equivalent for one record, for learning:
`aws route53 change-resource-record-sets --hosted-zone-id <zone> --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"appian.example.com","Type":"A","AliasTarget":{"HostedZoneId":"<alb-zone-id>","DNSName":"<alb-dns>","EvaluateTargetHealth":false}}}]}'`

---

## Step 8 - Tests
**What it does:** checks the three mTLS cases on the mTLS host, the plain CloudFront host, and the headers the app received.

```bash
cd $LAB
tests/run-tests.sh eks appian.$DOMAIN
#  PASS valid cert (Test User One) -> 200  "mapped_user": "Test User One", "header_family": "alb"
#  PASS no client cert -> rejected
#  PASS revoked cert (Test User Two) -> rejected

# See the raw X-Amzn-Mtls-Clientcert-* headers the ALB injected:
curl -s --cert pki/client-valid.pem --key pki/client-valid.key https://appian.$DOMAIN/whoami | python3 -m json.tool

# Spoofing check: forged headers are overwritten by the ALB (subject stays Test User One)
curl -s --cert pki/client-valid.pem --key pki/client-valid.key -H 'X-Amzn-Mtls-Clientcert-Subject: CN=Mallory' https://appian.$DOMAIN/whoami | grep mapped_user

# Non-mTLS host via CloudFront: 200, no client-cert headers, header_family null
curl -s https://app.$DOMAIN/public | python3 -m json.tool
curl -sI https://app.$DOMAIN/public | grep -i -E '^(x-cache|via)'      # proves it went through CloudFront
```
**Watch it in Argo CD:** open http://localhost:8080 → apps `aws-load-balancer-controller` and `mtls-echo` should be **Synced/Healthy**.
Click `mtls-echo` → the Ingress nodes show the ALB hostname, and the pod's live logs show each request. CLI: `argocd app get mtls-echo`, `kubectl -n mtls-echo logs -f deploy/mtls-echo`.
Try changing `identityField: serial` in values.yaml and pushing. Argo CD rolls the pod, and `mapped_user` becomes `1000`.

---

## Step 9 - Teardown (order matters)
**What it does:** removes everything in the order that avoids orphaned ALBs and stuck deletes. Terraform can't delete a VPC that still has a controller-made ALB in it.

```bash
# 1) CloudFront + DNS records first (they point at the ALB)
cd $LAB/terraform-eks-edge
sed -i 's/alb_ready = true/alb_ready = false/' terraform.tfvars && terraform apply    # CloudFront disable+delete takes ~5-15 min

# 2) Remove the Ingresses/apps via Git (Argo CD prunes them; the finalizer deletes the ALB)
#    set mtlsLab.enabled: false in gitops/apps/values.yaml, commit, push, then:
argocd app sync root
kubectl get ingress -A | grep mtls-echo || echo "ingresses gone"
# 3) Wait until the ALB is really gone (and its controller-made security groups)
watch -n 15 "aws elbv2 describe-load-balancers --query \"LoadBalancers[?contains(LoadBalancerName,'mtlslab')].LoadBalancerName\" --output text"

# 4) Trust store, CRL, S3, ACM cert, validation records
terraform destroy

# 5) Controller IAM (or keep it), then the whole EKS lab when you're done for the day
cd ~/path/to/eks-llm-lab/terraform
terraform apply -var enable_aws_lb_controller=false
terraform destroy          # per the eks-llm-lab README

# 6) Hosted zone ($0.50/mo) if you don't want it: delete its records first, then
aws route53 delete-hosted-zone --id <ZoneId>
# 7) Delete the lab access key: IAM -> Users -> mtls-lab -> Security credentials -> Delete. Check Billing the next day.
```
**Verify:** `aws elbv2 describe-load-balancers`, `aws elbv2 describe-trust-stores` and `aws cloudfront list-distributions` show nothing from the lab.

---

## Step 10 - What the added pieces cost (us-east-1, on top of the EKS lab's ~$0.38/hr)
| Item | ~$/hour |
|---|---|
| ALB (1, shared by both hosts) | 0.0225 + ~0.008 LCU |
| ALB public IPv4 x2 | 0.010 |
| ALB trust store association | ~0.005 (3rd-party summary of ELB pricing; verify) |
| CloudFront, S3, ACM public cert, LB controller + echo pods (fit on existing nodes) | ~0 at lab traffic |
| Route 53 hosted zone | $0.50/month (~0.0007/hr) + domain registration if you buy one |
| **Added total** | **≈ $0.046/hr (~$1.10/day)** |

---

### Notes / gotchas
- **Security-group rule quota:** the CloudFront prefix list counts as roughly 55 rules against the default 60 per SG. If the controller errors with `RulesPerSecurityGroupLimitExceeded`, raise the quota or drop `security-group-prefix-lists` and rely on the header rule.
- `drop_invalid_header_fields` is on, and the ALB **overwrites** `X-Amzn-Mtls-Clientcert-*`. The pod is reachable only through the ALB (target-type ip in private subnets). If you ever expose it another way, the identity headers become forgeable.
- To refresh a CRL: re-run make-pki / revoke, then `terraform apply` in `terraform-eks-edge` (new S3 object version → new revocation).
