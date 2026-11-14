#!/usr/bin/env python3
"""Mock 'Appian-like' echo backend (stdlib only, no pip installs).

It plays the role of the app that sits BEHIND the mTLS terminator (NetScaler today,
ALB or CloudFront tomorrow). It never sees the TLS handshake; it only sees the HTTP
headers the terminator injected. It echoes them back and shows which value it would
map to a user account, controlled by IDENTITY_FIELD:
  subject  -> CN parsed from the subject DN   (common NetScaler/Appian pattern)
  serial   -> certificate serial number
  dn       -> full subject DN string
  upn      -> email/UPN SAN parsed from the leaf PEM (PIV-style)

SECURITY NOTE: an app that trusts identity headers MUST only be reachable from the
terminator (security group / network policy), otherwise anyone can forge them.
"""
import json, os, re, ssl, tempfile, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IDENTITY_FIELD = os.environ.get("IDENTITY_FIELD", "subject")
PORT = int(os.environ.get("PORT", "8080"))
# Header families we understand. ALB verify mode == X-Amzn-Mtls-Clientcert-*,
# CloudFront viewer mTLS == CloudFront-Viewer-Cert-*.
FAMILIES = {
    "alb": {"subject": "X-Amzn-Mtls-Clientcert-Subject", "issuer": "X-Amzn-Mtls-Clientcert-Issuer",
            "serial": "X-Amzn-Mtls-Clientcert-Serial-Number", "validity": "X-Amzn-Mtls-Clientcert-Validity",
            "leaf": "X-Amzn-Mtls-Clientcert-Leaf"},
    "cloudfront": {"subject": "CloudFront-Viewer-Cert-Subject", "issuer": "CloudFront-Viewer-Cert-Issuer",
                   "serial": "CloudFront-Viewer-Cert-Serial-Number", "validity": "CloudFront-Viewer-Cert-Validity",
                   "leaf": "CloudFront-Viewer-Cert-Pem"},
}


def upn_from_pem(pem_urlencoded):
    if not pem_urlencoded:
        return None
    pem = urllib.parse.unquote(pem_urlencoded)
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(pem)
        path = f.name
    try:
        info = ssl._ssl._test_decode_cert(path)  # stdlib helper; fine for a lab
        for kind, val in info.get("subjectAltName", ()):
            if kind == "email":
                return val
    except Exception as e:  # noqa: BLE001
        return f"<could not parse leaf: {e}>"
    finally:
        os.unlink(path)
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            return self._send(200, {"ok": True})
        fam_name, fam = next(((n, f) for n, f in FAMILIES.items() if self.headers.get(f["subject"])), (None, None))
        cert = {k: self.headers.get(h) for k, h in fam.items()} if fam else {}
        if fam and cert.get("leaf"):
            cert["leaf"] = cert["leaf"][:60] + "...(truncated)"
        identity = None
        if fam:
            subj = self.headers.get(fam["subject"], "")
            m = re.search(r"(?:^|,)\s*CN=([^,]+)", subj)
            identity = {
                "subject": m.group(1) if m else None,
                "dn": subj,
                "serial": self.headers.get(fam["serial"]),
                "upn": upn_from_pem(self.headers.get(fam["leaf"])),
            }.get(IDENTITY_FIELD)
        body = {
            "app": "mock-appian",
            "path": self.path,
            "header_family": fam_name,
            "client_cert": cert,
            "identity_field": IDENTITY_FIELD,
            "mapped_user": identity,
            "authenticated": identity is not None,
            "all_mtls_headers": {k: (v[:60] + "...") if len(v) > 60 else v for k, v in self.headers.items()
                                 if k.lower().startswith(("x-amzn-mtls", "cloudfront-viewer-cert", "x-forwarded"))},
        }
        # /public/* mimics a non-mTLS app (CloudFront path): always 200, shows no identity.
        self._send(200 if identity or self.path.startswith("/public") else 401, body)

    def _send(self, code, body):
        data = json.dumps(body, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.client_address[0], fmt % args), flush=True)


if __name__ == "__main__":
    print(f"mock-appian listening on :{PORT}, IDENTITY_FIELD={IDENTITY_FIELD}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
