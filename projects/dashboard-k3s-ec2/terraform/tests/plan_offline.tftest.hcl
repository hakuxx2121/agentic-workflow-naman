# Offline plan test: a MOCK AWS provider, so no credentials and no API calls.
# Run: terraform init -backend=false && terraform test
mock_provider "aws" {
  # Use the mock values during plan too (the real provider knows these at plan time).
  override_during = plan

  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_route53_zone" {
    defaults = { zone_id = "Z0123456789EXAMPLE", name = "example.com" }
  }
  mock_resource "aws_vpc" {
    defaults = { ipv6_cidr_block = "2600:1f18:1234:5600::/56" }
  }
  mock_resource "aws_route53_zone" {
    defaults = { zone_id = "ZNEWZONEEXAMPLE", name_servers = ["ns-1.example.net"] }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::creator-dashboard-mock", bucket = "creator-dashboard-mock" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/mock/1", dns_name = "mock.elb.amazonaws.com", zone_id = "Z35SXDOTRQ7X7K" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/mock/1" }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
      domain_validation_options = [{
        domain_name           = "dash.example.com"
        resource_record_name  = "_abc.dash.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_xyz.acm-validations.aws."
      }]
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = { certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock" }
  }
  mock_resource "aws_wafv2_web_acl" {
    defaults = { arn = "arn:aws:wafv2:us-east-1:123456789012:regional/webacl/mock/1" }
  }
}

run "defaults_existing_zone_no_waf" {
  command = plan
  variables {
    existing_hosted_zone_id = "Z0123456789EXAMPLE"
  }

  assert {
    condition     = length(aws_route53_zone.this) == 0
    error_message = "must not create a zone when an existing one is given"
  }
  assert {
    condition     = length(aws_wafv2_web_acl.this) == 0
    error_message = "WAF must be off by default"
  }
  assert {
    condition     = aws_instance.k3s.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 must be required"
  }
  assert {
    condition     = aws_instance.k3s.root_block_device[0].encrypted && aws_instance.k3s.root_block_device[0].volume_type == "gp3"
    error_message = "root volume must be encrypted gp3"
  }
  assert {
    condition     = aws_instance.k3s.instance_type == "t4g.small"
    error_message = "default instance type"
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.node_from_alb.from_port == 30080 && aws_vpc_security_group_ingress_rule.node_from_alb.to_port == 30080
    error_message = "node SG must open only the NodePort"
  }
  assert {
    condition     = aws_lb_listener.https.ssl_policy == "ELBSecurityPolicy-TLS13-1-2-2021-06"
    error_message = "TLS 1.2+ policy"
  }
  assert {
    condition     = aws_lb_listener.http.default_action[0].type == "redirect"
    error_message = "port 80 must redirect"
  }
  assert {
    condition     = length(aws_route53_record.site_aaaa) == 1 && aws_lb.this.ip_address_type == "dualstack"
    error_message = "IPv6 alias + dualstack ALB expected by default"
  }
  assert {
    condition     = length(aws_subnet.public) == 2 && aws_subnet.public[0].availability_zone != aws_subnet.public[1].availability_zone
    error_message = "ALB needs two subnets in two AZs"
  }
  assert {
    condition     = strcontains(aws_instance.k3s.user_data, "--disable traefik") && strcontains(aws_instance.k3s.user_data, "kind: HelmChart")
    error_message = "user_data must install k3s without traefik, plus Argo CD"
  }
}

run "new_zone_waf_on_no_argocd" {
  command = plan
  variables {
    existing_hosted_zone_id = ""
    enable_waf              = true
    install_argocd          = false
    enable_ipv6             = false
  }

  assert {
    condition     = length(aws_route53_zone.this) == 1
    error_message = "should create a zone when none is given"
  }
  assert {
    condition     = length(aws_wafv2_web_acl.this) == 1 && length(aws_wafv2_web_acl_association.alb) == 1
    error_message = "WAF + association expected"
  }
  assert {
    condition     = !strcontains(aws_instance.k3s.user_data, "HelmChart")
    error_message = "Argo CD manifest must be skipped"
  }
  assert {
    condition     = length(aws_route53_record.site_aaaa) == 0 && aws_lb.this.ip_address_type == "ipv4"
    error_message = "no AAAA / ipv4 ALB when IPv6 is off"
  }
}

run "nodeport_out_of_range_rejected" {
  command = plan
  variables {
    node_port = 8080
  }
  expect_failures = [var.node_port]
}
