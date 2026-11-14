#!/usr/bin/env bash
# Fallback when Docker isn't available. Proves the two halves separately:
#  A) TLS layer: openssl s_server with the SAME trust bundle + CRLs rejects no-cert and revoked certs.
#  B) App layer: the mock backend maps ALB-style headers to a user and rejects requests without them.
set -uo pipefail
cd "$(dirname "$0")/.."
P=pki; ok=0; bad=0
res() { if [[ $1 == "$2" ]]; then echo "PASS  $3"; ((ok++)); else echo "FAIL  $3 (got $1)"; ((bad++)); fi; }

# s_server takes CRLs via a hashed CA directory (-CApath), so build one.
CAD=$(mktemp -d); cp $P/root-ca.pem $P/int/int-ca.pem $P/int-ca.crl.pem $P/root-ca.crl.pem "$CAD"/; openssl rehash "$CAD" 2>/dev/null
openssl s_server -accept 9443 -quiet -www -cert $P/server-chain.pem -key $P/server.key \
  -CApath "$CAD" -Verify 2 -verify_return_error -crl_check_all >/tmp/s_server.log 2>&1 &
SP=$!; sleep 1
c() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 --cacert $P/root-ca.pem "$@" https://localhost:9443/; }
res "$(c --cert $P/client-valid.pem --key $P/client-valid.key)" 200 "TLS: valid cert accepted"
res "$(c)"                                                         000 "TLS: no cert rejected in handshake"
res "$(c --cert $P/client-revoked.pem --key $P/client-revoked.key)" 000 "TLS: revoked cert rejected (CRL)"
kill $SP

IDENTITY_FIELD=${IDENTITY_FIELD:-subject} PORT=18080 python3 local/backend/app.py >/tmp/backend.log 2>&1 &
BP=$!; sleep 1
LEAF=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(open('$P/client-valid.pem').read(),safe='+=/'))")
SUBJ=$(openssl x509 -in $P/client-valid.pem -noout -subject -nameopt RFC2253 | sed 's/^subject=//')
body=$(curl -s -w '\n%{http_code}' http://127.0.0.1:18080/whoami \
  -H "X-Amzn-Mtls-Clientcert-Subject: $SUBJ" -H "X-Amzn-Mtls-Clientcert-Serial-Number: 1000" \
  -H "X-Amzn-Mtls-Clientcert-Leaf: $LEAF")
echo "$body" | grep -E '"(mapped_user|identity_field)"'
res "$(tail -n1 <<<"$body")" 200 "APP: identity headers -> 200 + mapped user"
res "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/whoami)" 401 "APP: no identity headers -> 401"
kill $BP
echo "== $ok passed, $bad failed"; [[ $bad -eq 0 ]]
