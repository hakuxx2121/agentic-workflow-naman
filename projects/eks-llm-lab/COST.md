# Cost estimate (us-east-1, looked up Oct 26, 2026)

**These are estimates.** Spot prices change every few minutes. "Month" means 730 hours left running.
Rows marked **≈** are approximate (a standard published rate I couldn't re-check on the live AWS page this session).

## Unit prices used

| Item | Price | Source |
|---|---|---|
| EKS control plane (standard support) | $0.10 /hr | https://aws.amazon.com/eks/pricing/ (verified) |
| NAT gateway | $0.045 /hr + $0.045 /GB processed | https://aws.amazon.com/vpc/pricing/ (verified via search excerpt of the AWS page) |
| Public IPv4 (NAT gateway's Elastic IP) | $0.005 /hr | https://aws.amazon.com/vpc/pricing/ ; https://www.factualminds.com/tools/aws-nat-gateway-pricing-calculator/ |
| t3.medium on-demand | $0.0416 /hr | https://ec2.shop/?region=us-east-1&filter=t3.medium (AWS list price) |
| m6i.large on-demand / spot | $0.096 / $0.0425 /hr | https://ec2.shop/?region=us-east-1&filter=m6i.large |
| m6i.xlarge on-demand / spot | $0.192 / $0.0845 /hr | https://ec2.shop/?region=us-east-1&filter=m6i.xlarge |
| c6i.xlarge on-demand / spot | $0.170 / $0.0783 /hr | https://ec2.shop/?region=us-east-1&filter=c6i.xlarge |
| g4dn.xlarge on-demand / spot | $0.526 / $0.2204 /hr | https://ec2.shop/?region=us-east-1&filter=g4dn.xlarge |
| g5.xlarge on-demand / spot | $1.006 / $0.5006 /hr | https://ec2.shop/?region=us-east-1&filter=g5.xlarge |
| g6.xlarge on-demand / spot | $0.8048 / ≈$0.105 /hr (unusually low, may be stale) | https://ec2.shop/?region=us-east-1&filter=g6.xlarge |
| EBS gp3 | ≈ $0.08 /GB-month | https://aws.amazon.com/ebs/pricing/ (≈) |
| Network Load Balancer (only if you add one) | ≈ $0.0225 /hr + LCU | https://aws.amazon.com/elasticloadbalancing/pricing/ (≈) |
| SQS + EventBridge (interruption queue) | ≈ $0 (free tier / pennies) | https://aws.amazon.com/sqs/pricing/ (≈) |

Spot prices are point-in-time averages reported by ec2.shop. Check the live price in EC2 → Spot Requests → Pricing history.

## Default CPU setup

Assumption: Karpenter launches **1× c6i.xlarge spot** for the model (3 vCPU request) and **1× m6i.large spot** for the monitoring stack.
It may pick a different c/m type; spot is usually in this range.

| Component | $/hour | $/month (730 h) |
|---|---|---|
| EKS control plane | 0.100 | 73.00 |
| NAT gateway (hourly) | 0.045 | 32.85 |
| NAT public IPv4 | 0.005 | 3.65 |
| 2× t3.medium system nodes (on-demand) | 0.083 | 60.74 |
| Karpenter c6i.xlarge spot | 0.078 | 57.16 |
| Karpenter m6i.large spot | 0.043 | 31.03 |
| EBS ≈140 GB gp3 (2×20 GB system + 2×50 GB Karpenter) ≈ | 0.015 | 11.20 |
| Load balancers | 0 (none; we use port-forward) | 0 |
| NAT data (images + 0.4 GB model, ~5 GB/day) ≈ | ~0.01 | ~6.75 |
| **Total** | **≈ $0.38 /hr** | **≈ $276 /month** |

If spot isn't available and Karpenter falls back to **on-demand** (c6i.xlarge $0.17 + m6i.large $0.096):
**≈ $0.52 /hr, ≈ $381 /month**.

**A typical 3-hour lab session costs ≈ $1.15 to $1.60.** Most of the monthly number comes from *forgetting to destroy*.
The cluster + NAT + system nodes alone are ≈ $0.23/hr (≈ $170/mo) even with no model running.

## GPU option (`enable_gpu_nodepool = true`)

Adds one GPU node (plus its 50 GB disk ≈ $0.005/hr) on top of the default setup.

| GPU node | Extra $/hr | Total $/hr | Total $/month |
|---|---|---|---|
| g4dn.xlarge **spot** (T4) | 0.225 | ≈ 0.61 | ≈ $441 |
| g4dn.xlarge on-demand | 0.531 | ≈ 0.91 | ≈ $665 |
| g6.xlarge on-demand (L4) | 0.810 | ≈ 1.19 | ≈ $869 |
| g5.xlarge on-demand (A10G) | 1.011 | ≈ 1.39 | ≈ $1,015 |

Karpenter picks the cheapest available type that fits, which is normally g4dn.xlarge spot. When the vLLM pod is removed
(GPU flag back to `false`), Karpenter consolidates the GPU node away within minutes.

## Ways to cut cost further
- Destroy when idle (biggest win). Re-creating takes ~20 min.
- Use one t3.medium for system nodes (`min_size/desired_size = 1`). Less resilient, saves ~$30/mo.
- Replace the NAT gateway with VPC endpoints plus public-subnet nodes (more complex; not done here to keep it simple).
