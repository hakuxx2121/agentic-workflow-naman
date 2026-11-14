#!/usr/bin/env bash
# mTLS acceptance tests. Same three checks everywhere:
#   1) valid cert   -> HTTP 200 + echoed identity
#   2) no cert      -> rejected (TLS handshake failure or HTTP 4xx)
#   3) revoked cert -> rejected
# Usage:
#   tests/run-tests.sh local                      # docker compose tier (https://localhost:8443)
#   tests/run-tests.sh aws                        # reads ALB DNS from `terraform output`
#   tests/run-tests.sh aws <alb-dns-name>         # or pass it explicitly
#   tests/run-tests.sh eks <mtls-host>             # EKS + AWS LB Controller front door
#   tests/run-tests.sh cloudfront-mtls <host>     # optional: CloudFront viewer mTLS distribution
set -uo pipefail
cd "$(dirname "$0")/.."
TARGET=${1:-local}
LAB_DOMAIN=${LAB_DOMAIN:-appian.lab.example.com}
PKI=pki
[[ -f $PKI/client-valid.pem ]] || { echo "Run scripts/make-pki.sh first"; exit 2; }

case $TARGET in
  local)
    URL="https://localhost:8443/whoami"; CURL_TLS=(--cacert $PKI/root-ca.pem) ;;
  aws)
    ALB=${2:-$(terraform -chdir=terraform output -raw alb_dns_name 2>/dev/null)}
    [[ -n $ALB ]] || { echo "No ALB DNS name"; exit 2; }
    # Use the fake hostname so the lab server cert validates, but connect to the ALB.
    URL="https://${LAB_DOMAIN}/whoami"; CURL_TLS=(--cacert $PKI/root-ca.pem --connect-to "${LAB_DOMAIN}:443:${ALB}:443") ;;
  eks)
    # EKS front door (docs/eks-cloudfront-step-by-step.md): real public ACM cert, so no --cacert.
    URL="https://${2:?pass the mTLS host, e.g. appian.example.com}/whoami"; CURL_TLS=() ;;
  cloudfront-mtls)
    URL="https://${2:?pass the distribution host}/whoami"; CURL_TLS=() ;;
  *) echo "unknown target $TARGET"; exit 2 ;;
esac

pass=0; fail=0
check() { # name, expect(accept|reject), extra curl args...
  local name=$1 expect=$2; shift 2
  local out code
  out=$(curl -sS --max-time 15 "${CURL_TLS[@]}" "$@" -w '\n%{http_code}' "$URL" 2>&1); rc=$?
  code=$(tail -n1 <<<"$out")
  if [[ $expect == accept ]]; then
    if [[ $rc -eq 0 && $code == 200 ]] && grep -q '"mapped_user"' <<<"$out"; then
      echo "PASS  $name -> 200"; grep -E '"(mapped_user|identity_field|header_family)"' <<<"$out" | sed 's/^/        /'; ((pass++))
    else echo "FAIL  $name (rc=$rc code=$code)"; echo "$out" | head -20 | sed 's/^/        /'; ((fail++)); fi
  else
    if [[ $rc -ne 0 || $code =~ ^4 ]]; then
      echo "PASS  $name -> rejected (curl rc=$rc http=$code)"; ((pass++))
    else echo "FAIL  $name was NOT rejected (code=$code)"; echo "$out" | head -10 | sed 's/^/        /'; ((fail++)); fi
  fi
}

echo "Target: $TARGET  URL: $URL"
check "valid cert (Test User One)"   accept --cert $PKI/client-valid.pem   --key $PKI/client-valid.key
check "no client cert"               reject
check "revoked cert (Test User Two)" reject --cert $PKI/client-revoked.pem --key $PKI/client-revoked.key
echo "== $pass passed, $fail failed"
[[ $fail -eq 0 ]]
