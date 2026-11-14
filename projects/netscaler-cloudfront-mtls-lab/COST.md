# Cost (us-east-1, on-demand list prices, estimated 2026-10-29. Check the pricing pages)

| Item | ~$/hour | Notes |
|---|---|---|
| ALB | 0.0225 | + LCU, about $0.008/hr at lab traffic |
| ALB public IPv4 (2 AZs) | 0.010 | $0.005/hr per public IPv4 |
| ALB trust store association | 0.005 | per a 3rd-party summary of ELB pricing. Verify |
| EC2 t4g.nano + its public IPv4 | 0.0042 + 0.005 | |
| EBS 8 GB gp3 | 0.001 | |
| CloudFront (1 or 2 distributions), S3, ACM import | ~0 | pay per request/GB; idle ~ $0 |
| **Total** | **≈ $0.055/hr** | **≈ $1.30/day, ≈ $40/month if forgotten** |

The local docker tier is free. Run `terraform destroy` when you're done.
