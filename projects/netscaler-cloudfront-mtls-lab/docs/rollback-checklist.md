# Rollback checklist

**Trigger examples:** users mapped to wrong account (stop right away), login failure rate above the agreed threshold,
revocation not enforced, ALB/trust store errors.

- [ ] Before cutover: confirm the NetScaler vServer is still **configured and healthy** (not deleted, certs not expired)
- [ ] Before cutover: DNS TTL at 60s and confirmed propagated (`dig +noall +answer <record>` shows the low TTL)
- [ ] Before cutover: rollback owner, DNS owner and Appian owner on the bridge; DNS change pre-staged
- [ ] Rollback step 1: set Route 53 weights back to NetScaler 100 / ALB 0 (or revert the record)
- [ ] Rollback step 2: wait at least 1x TTL plus client cache. Note that browsers keep TLS connections open, so users may need to restart the browser or wait for idle timeout
- [ ] Rollback step 3: confirm logins via NetScaler logs; ALB request count trending to zero
- [ ] If the problem was identity mapping: identify affected sessions/accounts from Appian audit logs and ALB access logs
- [ ] Keep the ALB stack up (don't `destroy`) for root-cause analysis
- [ ] Write it up; fix; repeat the parallel run before the next attempt
