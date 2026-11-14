# Research notes & option comparison (verified 2026-10-29)

Everything below was checked against AWS docs/announcements on 2026-10-29. Items marked
**UNVERIFIED** I could not confirm from an official source - confirm with AWS (TAM/SA) before relying on them.

## 1. CloudFront viewer mTLS - current state

| Question | Answer | Source |
|---|---|---|
| Is it available? | Yes. Launched **24 Nov 2025** (announced as a standard feature, not "preview"). | [AWS blog: launch](https://aws.amazon.com/blogs/networking-and-content-delivery/trust-goes-both-ways-amazon-cloudfront-now-supports-viewer-mtls/) |
| Modes | **Required** (no/invalid cert -> connection refused), **Optional** (invalid cert refused, no cert allowed), **Passthrough** (added 14 May 2026: no trust store, CloudFront only checks key possession, forwards chain to origin, *no caching*). | [Docs: mTLS](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/mtls-authentication.html), [What's New: passthrough](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-cloudfront-mtls-passthrough/) |
| Trust store | Account-level resource built from a PEM CA bundle in S3; reused across distributions. | [Docs: trust stores](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/trust-stores-certificate-management.html) |
| Limits | 20 trust stores/account (raisable), 300 distributions/trust store, **CA bundle 1 MB, max 25 CA certs per bundle**, chain depth 4. | [Docs: quotas](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-limits.html) |
| Distribution requirements | **All** cache behaviors must be HTTPS-only / redirect-to-HTTPS; HTTP/2 (mTLS not supported on HTTP/3). Console can't enable it during create - edit after. | [Docs: enable mTLS](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/enable-mtls-distributions.html) |
| Price classes | No price-class restriction found in the docs. **UNVERIFIED** (absence of a restriction, not a stated support). |  |
| Default `*.cloudfront.net` domain OK? | Docs don't state an alias is required. **UNVERIFIED** - the lab supports both. |  |
| Revocation | **No CRL upload** (unlike ALB). Two mechanisms: (a) **OCSP** checking, added **14 May 2026** - CloudFront queries the responder URL in the cert (AIA), caches answers up to 30 min, result exposed in the connection function; (b) **connection function + KeyValueStore** deny-list of serials that you maintain yourself. | [What's New: OCSP](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-cloudfront-mtls-ocsp/), [launch blog](https://aws.amazon.com/blogs/networking-and-content-delivery/trust-goes-both-ways-amazon-cloudfront-now-supports-viewer-mtls/) |
| OCSP failure behaviour (responder down = fail open or closed?) | **UNVERIFIED** - not stated in the announcement. Important for CAC/PIV. |  |
| Headers to origin | `CloudFront-Viewer-Cert-Serial-Number`, `-Issuer` (RFC2253), `-Subject` (RFC2253), `-Present`, `-Sha256`, `-Validity`, `-Pem` (URL-encoded leaf, origin only). Passthrough adds `Client-Cert` and `Client-Cert-Chain`. You must add them to an **origin request policy**. | [Docs: mTLS headers](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/viewer-mtls-headers.html) |
| Terraform | `aws_cloudfront_trust_store` since AWS provider **v6.27.0** (17 Dec 2025); `viewer_mtls_config` + `connection_function_association` on `aws_cloudfront_distribution` since **v6.29.0**. Lab validated with **v6.71.0**. Provider schema: `mode` = `required`/`optional` (passthrough not shown in the registry docs - **UNVERIFIED** in Terraform). | [Registry: trust store](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudfront_trust_store), [Registry: distribution](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudfront_distribution), [CHANGELOG 6.29.0](https://github.com/hashicorp/terraform-provider-aws/blob/v6.29.0/CHANGELOG.md), [6.27.0 notes](https://github.com/hashicorp/terraform-provider-aws/blob/v6.38.0/.changes/6.x/6.27.0.md) |
| Cost | OCSP and passthrough announced "at no additional cost". On **flat-rate plans**, viewer mTLS is **Premium tier only**. On pay-as-you-go I found **no published separate mTLS fee - UNVERIFIED**; check the pricing page/your bill. | [Flat-rate blog](https://aws.amazon.com/blogs/networking-and-content-delivery/amazon-cloudfront-flat-rate-pricing-plans-new-features-and-expanded-capabilities/), [flat-rate docs](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/flat-rate-pricing-plan.html) |
| Logs | Connection logs (TLS handshake, cert info, `connectionId`) via CloudWatch vended logs. | launch blog |

## 2. ALB mTLS

| Question | Answer | Source |
|---|---|---|
| Modes | **Verify** (ALB validates against a trust store) and **Passthrough** (ALB sends whole chain to target in `X-Amzn-Mtls-Clientcert`, target validates). | [ALB mTLS docs](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/mutual-authentication.html) |
| Trust store | `aws_lb_trust_store`: PEM bundle in S3, one bundle per store, replace via ModifyTrustStore. No blank lines; comments must not contain `-`. | [Configure ALB mTLS](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/configuring-mtls-with-elb.html) |
| CRL | **Yes, native**: PEM CRLs in S3 added to the trust store (`aws_lb_trust_store_revocation`). Can't revoke negative serials. Quotas (3rd-party summary of the quota page): 25 CA certs/trust store, 30 CRLs, 500k revocation entries, 50 MB CRL. **No OCSP.** CRLs are static: you must re-upload when the CA publishes a new one. | same; [ALB quotas](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-limits.html) |
| Headers (verify) | `X-Amzn-Mtls-Clientcert-Serial-Number`, `-Issuer`, `-Subject` (RFC2253), `-Validity`, `-Leaf` (URL-encoded PEM). | ALB mTLS docs |
| Gotchas | No TLS session resumption with mTLS. Connection logs available. | ALB mTLS docs |
| Cost | Normal ALB hourly + LCU, plus a **trust-store association hourly fee** (~$0.005/hr in us-east-1 per a third-party summary - **verify** on the ELB pricing page). | [ELB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/) |

## 3. NLB TCP passthrough (brief)
An NLB **TCP** listener on 443 never decrypts, so the client cert goes straight through to the app tier
(e.g. an ingress controller / Appian web tier doing `ssl_verify_client` + CRL/OCSP itself).
Pros: the app tier keeps full control (OCSP, CRL, any custom mapping), identical to how many NetScaler
"SSL bridge" setups work. Cons: no WAF, no L7 routing at AWS, you own certs/CRL refresh/TLS policy in the
pods, client IP needs proxy protocol, and nothing AWS-native in the auth path to audit.
([NLB listeners](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/load-balancer-listeners.html))

## 4. Plain-language comparison

| | Option 1: mTLS at CloudFront | Option 2: Appian -> ALB mTLS verify (+CRL), rest on CloudFront | Option 3: NLB passthrough, app does mTLS |
|---|---|---|---|
| Where the CAC is checked | AWS edge | ALB in your VPC | Your pods |
| Revocation | OCSP (since May 2026) or DIY deny-list. **No CRL file.** | **CRL** (static upload, you automate refresh). No OCSP. | Whatever you configure (CRL and/or OCSP) |
| CA bundle limit | 25 certs | 25 certs | none (your server) |
| Identity header to Appian | `CloudFront-Viewer-Cert-*` | `X-Amzn-Mtls-Clientcert-*` | whatever your ingress sets |
| WAF / DDoS | CloudFront + WAF | WAF on ALB, Shield Std | none at L7 |
| Maturity | Newest (Nov 2025; OCSP/passthrough May 2026) | GA since late 2023, well-trodden | Oldest pattern |
| Ops burden | Low, but OCSP fail-mode unknown | Medium (CRL refresh job) | Highest |
| One front door for all apps | Yes | Two front doors (DNS split) | Two front doors |

### Recommendation
**Option 2 now, with Option 1 as a tracked follow-up.** Reasons:
1. Federal CAC/PIV auth normally needs a documented revocation check. ALB has a native CRL check today; CloudFront
   has no CRL support, and its OCSP feature is about six months old with an undocumented fail-open/fail-closed behaviour.
2. The ALB headers map almost 1:1 onto what NetScaler cert-to-header policies usually inject (subject, issuer,
   serial, PEM), so Appian's change stays small.
3. The other apps still get CloudFront. Only Appian's hostname points somewhere else.
4. Everything is in Terraform with a mature provider.

Re-check Option 1 once AWS documents the OCSP fail behaviour and you confirm the responders are reachable from the
edge. It removes the second front door.

**Risk shared by Options 1 and 2:** both cap a trust store at **25 CA certs**. A full DoD/Federal PKI bundle may have more
CAs than that. Count the CAs Appian actually trusts today (discovery checklist). If you're over 25, you need a quota
increase or multiple listeners/trust stores, or Option 3.

**Must confirm for your environment:** CloudFront is a global (commercial-partition) service and **isn't in AWS GovCloud (US)**.
If the DOL workloads live in GovCloud, Option 1 and the CloudFront half of Option 2 need an ATO/boundary conversation.
I didn't verify that against your environment.

## 5. Test status at handoff (2026-10-29)
- PASS `tests/smoke-no-docker.sh`: the TLS layer (openssl s_server, same bundle + CRLs) accepted the valid cert, rejected no-cert, and rejected the revoked cert (`verify error:num=23:certificate revoked`). The app layer mapped the user correctly for subject/serial/dn/upn and returned 401 without headers.
- PASS `terraform fmt` + `terraform validate` (Terraform 1.13.4, AWS provider 6.71.0, `init -backend=false`).
- NOT TESTED: the docker compose / nginx tier (Docker couldn't be installed on the build box), any AWS apply, CloudFront viewer mTLS behaviour.
