data "aws_route53_zone" "domain_zone" {
  provider     = aws.route53
  name         = var.hosted_zone_name
  private_zone = false
}

resource "aws_route53_record" "www" {
  provider = aws.route53
  zone_id  = data.aws_route53_zone.domain_zone.zone_id
  name     = var.frontend_domain
  type     = "A"

  alias {
    name                   = aws_cloudfront_distribution.s3_distribution.domain_name
    zone_id                = aws_cloudfront_distribution.s3_distribution.hosted_zone_id
    evaluate_target_health = false
  }
}
