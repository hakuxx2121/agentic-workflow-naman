resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.argocd_chart_version
  wait             = true

  values = [yamlencode({
    # Keep Argo CD on the always-on system nodes.
    global = { nodeSelector = { "node-role/system" = "true" } }
    configs = {
      params = { "server.insecure" = true } # we only reach it via kubectl port-forward
    }
    dex           = { enabled = false }
    notifications = { enabled = false }
  })]

  depends_on = [helm_release.karpenter_nodepools]
}

# The "root" Application (app-of-apps). It points at gitops/apps in YOUR repo,
# which in turn creates one Application per component.
resource "helm_release" "argocd_bootstrap" {
  name      = "argocd-bootstrap"
  namespace = "argocd"
  chart     = "${path.module}/charts/argocd-bootstrap"

  values = [yamlencode({
    repoURL        = var.gitops_repo_url
    targetRevision = var.gitops_revision
    gpuEnabled     = var.enable_gpu_nodepool
  })]

  depends_on = [helm_release.argocd]
}
