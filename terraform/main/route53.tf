data "aws_route53_zone" "domain_zone" {
  provider     = aws.route53
  name         = var.hosted_zone_name
  private_zone = false
}

resource "aws_route53_record" "www" {
  provider = aws.route53
  zone_id  = data.aws_route53_zone.domain_zone.zone_id
  name     = var.qdrant_domain_name
  type     = "A"
  ttl      = "300"
  records  = [aws_eip.lb.public_ip]
}
