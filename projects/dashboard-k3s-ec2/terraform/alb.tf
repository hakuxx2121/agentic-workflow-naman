# Internet-facing ALB: :80 redirects to :443, :443 terminates TLS with the ACM cert
# and forwards to the k3s node's NodePort (nginx).

resource "aws_lb" "this" {
  name               = substr("${local.name}-alb", 0, 32)
  load_balancer_type = "application"
  internal           = false
  ip_address_type    = var.enable_ipv6 ? "dualstack" : "ipv4"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  drop_invalid_header_fields = true
  enable_deletion_protection = false # lab: lets `terraform destroy` remove it
  idle_timeout               = 60

  depends_on = [aws_internet_gateway.this]
}

resource "aws_lb_target_group" "nginx" {
  name        = substr("${local.name}-nginx", 0, 32)
  port        = var.node_port
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = aws_vpc.this.id

  deregistration_delay = 15

  health_check {
    path                = "/healthz" # served by nginx only after the first S3 sync finished
    port                = "traffic-port"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group_attachment" "node" {
  target_group_arn = aws_lb_target_group.nginx.arn
  target_id        = aws_instance.k3s.id
  port             = var.node_port
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  # TLS 1.3 + 1.2 only (no TLS 1.0/1.1).
  ssl_policy      = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn = aws_acm_certificate_validation.site.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.nginx.arn
  }
}
