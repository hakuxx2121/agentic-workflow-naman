#!/usr/bin/env bash
# Builds a FAKE, lab-only PKI that mimics a CAC/PIV-style hierarchy:
#   Root CA -> Intermediate (issuing) CA -> client certs (one valid, one revoked)
# plus a CRL per CA, and a server cert for the local nginx / ALB listener.
# Everything lands in ./pki (gitignored). Safe to re-run: it wipes and rebuilds.
set -euo pipefail
cd "$(dirname "$0")/.."
LAB_DOMAIN="${LAB_DOMAIN:-appian.lab.example.com}"   # fake hostname for the server cert
OUT=pki
rm -rf "$OUT"; mkdir -p "$OUT"/{root,int}
for ca in root int; do : > "$OUT/$ca/index.txt"; echo 1000 > "$OUT/$ca/serial"; echo 1000 > "$OUT/$ca/crlnumber"; done

# Minimal openssl "ca" config so we can revoke certs and generate CRLs.
cat > "$OUT/ca.cnf" <<CNF
[ ca ]
default_ca = CA_default
[ CA_default ]
dir             = \$ENV::CADIR
database        = \$dir/index.txt
serial          = \$dir/serial
crlnumber       = \$dir/crlnumber
new_certs_dir   = \$dir
default_md      = sha256
default_days    = 365
default_crl_days= 30
policy          = policy_any
copy_extensions = copy
[ policy_any ]
commonName = supplied
organizationName = optional
organizationalUnitName = optional
countryName = optional
[ v3_int ]
basicConstraints = critical,CA:true,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
[ v3_client ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
[ v3_server ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:${LAB_DOMAIN},DNS:localhost,IP:127.0.0.1
CNF
CNF="$OUT/ca.cnf"

echo "== Root CA"
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
  -subj "/C=US/O=Example Agency/OU=Lab PKI/CN=Example Agency Test Root CA" \
  -addext "basicConstraints=critical,CA:true" -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout "$OUT/root/root-ca.key" -out "$OUT/root/root-ca.pem" 2>/dev/null

echo "== Intermediate (issuing) CA"
openssl req -new -newkey rsa:3072 -nodes -subj "/C=US/O=Example Agency/OU=Lab PKI/CN=Example Agency Test Issuing CA 1" \
  -keyout "$OUT/int/int-ca.key" -out "$OUT/int/int-ca.csr" 2>/dev/null
CADIR="$OUT/root" openssl ca -batch -config "$CNF" -extensions v3_int -days 1825 \
  -cert "$OUT/root/root-ca.pem" -keyfile "$OUT/root/root-ca.key" \
  -in "$OUT/int/int-ca.csr" -out "$OUT/int/int-ca.pem" -notext 2>/dev/null

issue_client() { # name, CN, UPN
  local name=$1 cn=$2 upn=$3
  openssl req -new -newkey rsa:2048 -nodes \
    -subj "/C=US/O=Example Agency/OU=People/CN=$cn" \
    -addext "subjectAltName=otherName:1.3.6.1.4.1.311.20.2.3;UTF8:$upn,email:$upn" \
    -keyout "$OUT/$name.key" -out "$OUT/$name.csr" 2>/dev/null
  CADIR="$OUT/int" openssl ca -batch -config "$CNF" -extensions v3_client \
    -cert "$OUT/int/int-ca.pem" -keyfile "$OUT/int/int-ca.key" \
    -in "$OUT/$name.csr" -out "$OUT/$name.pem" -notext 2>/dev/null
}
echo "== Client certs"
issue_client client-valid   "Test User One" "test.user.one@example.test"
issue_client client-revoked "Test User Two" "test.user.two@example.test"

echo "== Revoke Test User Two, build CRLs"
CADIR="$OUT/int" openssl ca -config "$CNF" -cert "$OUT/int/int-ca.pem" -keyfile "$OUT/int/int-ca.key" \
  -revoke "$OUT/client-revoked.pem" -crl_reason keyCompromise 2>/dev/null
CADIR="$OUT/int"  openssl ca -gencrl -config "$CNF" -cert "$OUT/int/int-ca.pem"  -keyfile "$OUT/int/int-ca.key"  -out "$OUT/int-ca.crl.pem" 2>/dev/null
CADIR="$OUT/root" openssl ca -gencrl -config "$CNF" -cert "$OUT/root/root-ca.pem" -keyfile "$OUT/root/root-ca.key" -out "$OUT/root-ca.crl.pem" 2>/dev/null

echo "== Server cert for ${LAB_DOMAIN} / localhost"
openssl req -new -newkey rsa:2048 -nodes -subj "/C=US/O=Example Agency/CN=${LAB_DOMAIN}" \
  -keyout "$OUT/server.key" -out "$OUT/server.csr" 2>/dev/null
CADIR="$OUT/int" openssl ca -batch -config "$CNF" -extensions v3_server \
  -cert "$OUT/int/int-ca.pem" -keyfile "$OUT/int/int-ca.key" \
  -in "$OUT/server.csr" -out "$OUT/server.pem" -notext 2>/dev/null

# Bundles. NOTE: ALB requires no blank lines/comments with dashes in the bundle.
cp "$OUT/root/root-ca.pem" "$OUT/root-ca.pem"
cat "$OUT/int/int-ca.pem" "$OUT/root/root-ca.pem" > "$OUT/ca-bundle.pem"        # trust store (ALB / CloudFront / nginx)
cat "$OUT/int-ca.crl.pem" "$OUT/root-ca.crl.pem"  > "$OUT/crl-chain.pem"        # nginx checks every level
cat "$OUT/server.pem" "$OUT/int/int-ca.pem"        > "$OUT/server-chain.pem"     # served chain
openssl crl -in "$OUT/int-ca.crl.pem" -outform DER -out "$OUT/int-ca.crl.der"   # handy for inspection
rm -f "$OUT"/*.csr "$OUT"/int/*.csr

echo
echo "Done. Key files in ./pki:"
echo "  ca-bundle.pem        trust store bundle (intermediate + root)"
echo "  int-ca.crl.pem       CRL of the issuing CA (lists Test User Two) -> ALB revocation list"
echo "  client-valid.{pem,key}    Test User One  (serial $(openssl x509 -in $OUT/client-valid.pem -noout -serial | cut -d= -f2))"
echo "  client-revoked.{pem,key}  Test User Two  (serial $(openssl x509 -in $OUT/client-revoked.pem -noout -serial | cut -d= -f2), REVOKED)"
echo "  server-chain.pem / server.key   TLS server cert for ${LAB_DOMAIN}"
openssl verify -CAfile "$OUT/ca-bundle.pem" -crl_check_all -CRLfile "$OUT/crl-chain.pem" "$OUT/client-valid.pem" "$OUT/client-revoked.pem" || true
