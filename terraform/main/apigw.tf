resource "aws_apigatewayv2_api" "rag_api" {
  name          = local.api_name
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "rag_lambda" {
  api_id                 = aws_apigatewayv2_api.rag_api.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.rag.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "query" {
  api_id    = aws_apigatewayv2_api.rag_api.id
  route_key = "POST /query"

  target = "integrations/${aws_apigatewayv2_integration.rag_lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.rag_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_domain_name" "rag_api" {
  domain_name = var.apigw_domain_name

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.cert.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "rag_api" {
  api_id      = aws_apigatewayv2_api.rag_api.id
  domain_name = aws_apigatewayv2_domain_name.rag_api.id
  stage       = aws_apigatewayv2_stage.default.id
}
