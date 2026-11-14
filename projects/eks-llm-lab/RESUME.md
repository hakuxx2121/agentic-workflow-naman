# Resume bullets (personal project)

Use these **only after you've actually deployed it**, and change the numbers to the ones you measured.

**Personal Project: Self-hosted LLM platform on AWS EKS** (Terraform, Karpenter, Argo CD, OpenTelemetry)

- Built a reproducible AWS environment (VPC, EKS 1.36, IAM/Pod Identity, SQS interruption queue) with **Terraform** using
  community modules, bootstrapping **Argo CD** app-of-apps GitOps so all cluster add-ons and workloads deploy from Git.
- Served an open-source LLM (Qwen2.5-0.5B via llama.cpp, optional vLLM on GPU) with **Karpenter** spot-first NodePools that
  provision capacity on demand and consolidate when idle, keeping the lab at about $0.38/hr *(replace with your measured cost)*.
- Instrumented the stack with an **OpenTelemetry Collector** (kubelet stats, container logs, Prometheus scrapes) feeding
  Prometheus, Loki, and Grafana, and built a dashboard for p95 request latency, tokens/sec, resource usage, and node count
  *(add a measured figure, e.g. "~N tokens/s on c6i.xlarge spot")*.
