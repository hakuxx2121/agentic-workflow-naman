# NetScaler discovery checklist (Appian / client-cert auth)

Fill this in from the current NetScaler config (`show ssl vserver <name>`, `show ssl profile`,
`show rewrite policy`, `show ssl certKey`). Use placeholders in any shared notes, not real hostnames or IPs.

## A. TLS handling
- [ ] vServer type: **SSL (terminate)**, **SSL_BRIDGE (pass-through)**, or **TCP**? -> picks Option 2 vs 3
- [ ] Client auth setting: `clientAuth ENABLED`, `clientCert MANDATORY` or `OPTIONAL`?
- [ ] Is client auth on the whole vServer or only certain URLs (SSL policy with `CLIENT.SSL.CLIENT_CERT` / renegotiation)?
      ALB and CloudFront can't do per-path renegotiation. That needs a separate hostname.
- [ ] Back-end leg: does NetScaler re-encrypt to Appian (HTTPS) or plain HTTP? Does Appian itself require a cert from NetScaler?
- [ ] TLS versions/ciphers in the SSL profile vs. ALB policy `ELBSecurityPolicy-TLS13-1-2-2021-06` (or a FIPS policy)
- [ ] Session reuse relied on? (ALB mTLS: no session resumption)

## B. Trust chain
- [ ] List every CA certKey linked as `-CA` to the vServer. **Count them** (AWS trust store max = 25)
- [ ] Where do they come from (DoD PKE bundle, Federal Common Policy, agency CA)? Who refreshes them, and how often?
- [ ] Any `ocspValidation`/`crlCheck` settings on the CA certKeys?

## C. Revocation
- [ ] CRL: `show ssl crl`. Source URL, refresh interval, `crlCheck` = Mandatory/Optional?
- [ ] OCSP: `show ssl ocspResponder`. URL, caching, fail behaviour (responder down = allow or deny?)
- [ ] Is the CRL reachable from AWS (internet/VPC egress)? How big is it (ALB limit 50 MB)?

## D. Identity mapping (the most important part)
- [ ] Rewrite/cert-to-header policies: `show rewrite action`. Look for `CLIENT.SSL.CLIENT_CERT.SUBJECT`, `.SERIALNUMBER`, `.TO_PEM`, `.SUBJECT_ALTNAME`...
- [ ] Exact header names injected (e.g. `X-Client-Cert-Subject`, `SSL_CLIENT_S_DN`); value format (DN order! RFC2253 vs OpenSSL "/C=US/O=..." style)
- [ ] Which field does Appian map to a user: **subject DN / CN**, **serial**, **UPN from SAN (otherName 1.3.6.1.4.1.311.20.2.3)**, email SAN, or EDIPI parsed from CN?
- [ ] Where is that mapping configured in Appian (header-based SSO / custom auth plugin / reverse-proxy auth)?
- [ ] Does NetScaler strip inbound copies of those headers (spoofing protection)?
- [ ] Any second factor or SAML after cert auth?

## E. Traffic & ops
- [ ] Hostnames served by this vServer (record as placeholders), current DNS TTLs, who owns DNS
- [ ] Peak conn/s and concurrent users (sizing/LCU)
- [ ] Health monitors, stickiness/persistence (Appian session affinity?)
- [ ] Logs used for audit (cert subject per request?), where they go (Splunk?) -> ALB connection logs + access logs
- [ ] Maintenance windows, change board, ATO/boundary docs that name NetScaler
