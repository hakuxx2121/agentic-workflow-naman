# "VPC-lite": one VPC, two public subnets (the ALB requires two AZs), an internet gateway, and no NAT gateway.
# The k3s node sits in a public subnet with a public IPv4 so it can reach SSM, S3 and container registries
# outbound, but its security group allows NO inbound traffic except the NodePort from the ALB.

resource "aws_vpc" "this" {
  cidr_block                       = var.vpc_cidr
  enable_dns_support               = true
  enable_dns_hostnames             = true
  assign_generated_ipv6_cidr_block = var.enable_ipv6

  tags = { Name = local.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = local.name }
}

resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.this.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index) # 10.60.0.0/24, 10.60.1.0/24
  map_public_ip_on_launch = false                                    # set per-instance instead

  ipv6_cidr_block                 = var.enable_ipv6 ? cidrsubnet(aws_vpc.this.ipv6_cidr_block, 8, count.index) : null
  assign_ipv6_address_on_creation = false

  tags = { Name = "${local.name}-public-${local.azs[count.index]}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  dynamic "route" {
    for_each = var.enable_ipv6 ? [1] : []
    content {
      ipv6_cidr_block = "::/0"
      gateway_id      = aws_internet_gateway.this.id
    }
  }

  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Free S3 gateway endpoint: S3 traffic from the node stays on the AWS network.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]
  tags              = { Name = "${local.name}-s3" }
}

# ---------- Security groups ----------
# Separate rule resources (not inline blocks) so the two groups can reference each other without a cycle.

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Public ALB: 80/443 from the internet, egress only to the k3s NodePort"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${local.name}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_http_v4" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP (redirected to HTTPS)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_v4" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "alb_http_v6" {
  count             = var.enable_ipv6 ? 1 : 0
  security_group_id = aws_security_group.alb.id
  description       = "HTTP over IPv6 (redirected to HTTPS)"
  cidr_ipv6         = "::/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_v6" {
  count             = var.enable_ipv6 ? 1 : 0
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS over IPv6"
  cidr_ipv6         = "::/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "alb_to_node" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Forward + health checks to the nginx NodePort only"
  referenced_security_group_id = aws_security_group.node.id
  ip_protocol                  = "tcp"
  from_port                    = var.node_port
  to_port                      = var.node_port
}

resource "aws_security_group" "node" {
  name        = "${local.name}-node"
  description = "k3s node: no SSH, no 80/443. Only the NodePort from the ALB SG. Outbound for SSM, S3, image pulls."
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${local.name}-node" }
}

resource "aws_vpc_security_group_ingress_rule" "node_from_alb" {
  security_group_id            = aws_security_group.node.id
  description                  = "nginx NodePort, from the ALB security group only"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = var.node_port
  to_port                      = var.node_port
}

resource "aws_vpc_security_group_egress_rule" "node_all_v4" {
  security_group_id = aws_security_group.node.id
  description       = "Outbound: SSM agent, S3, k3s install, container images, OS updates"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
