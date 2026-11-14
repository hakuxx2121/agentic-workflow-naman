# Cutover plan (Option 2: Appian -> ALB mTLS verify; others -> CloudFront)

## Phase 0 - Prereqs (weeks before)
1. Discovery checklist complete. Identity field and header format agreed with the Appian team.
2. CA bundle built (<= 25 certs or quota plan). CRL refresh job (EventBridge schedule -> Lambda: download CRL -> S3 -> `ModifyTrustStore`/add revocation) built and tested.
3. ALB + trust store + listener in Terraform. WAF attached. Access logs + connection logs on.
4. Appian (or a header-translation layer) reads `X-Amzn-Mtls-Clientcert-*`. If Appian expects NetScaler's header names,
   add ALB listener-rule transforms or a small reverse proxy/ingress that renames them. Never trust headers from anything but the ALB SG.
5. Lower DNS TTL on the Appian record to **60s** at least 2x the old TTL before cutover.

## Phase 1 - Parallel run
6. Publish a test hostname (e.g. `appian-new.<internal-zone>`) on the ALB. Test users run the `tests/run-tests.sh` equivalents plus real CAC logins.
7. Compare: mapped user identical vs NetScaler for N pilot users (subject string byte-for-byte, serial case/leading zeros!).
8. Revocation test with a known-revoked test card/cert.

## Phase 2 - Gradual shift
9. Route 53 **weighted** records: NetScaler 90 / ALB 10 -> 50/50 -> 0/100 over agreed windows, watching 4xx/5xx, TLS handshake errors in connection logs, and Appian login failures.
   (If DNS isn't Route 53, do a single flip with low TTL instead.)
10. Other apps: move each hostname to CloudFront the same way, separately from Appian.

## Phase 3 - Cleanup
11. Keep NetScaler config intact (disabled vServer) for the agreed rollback window (e.g. 2 weeks).
12. Raise TTLs back. Update ATO/boundary diagrams. Decommission.

## Go/no-go criteria
- 100% of pilot users map to the same Appian account as before
- Revoked test cert rejected; CRL refresh job alarm wired
- No increase in login failure rate over the 10% step for 24h
