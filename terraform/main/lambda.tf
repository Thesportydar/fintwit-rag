data "archive_file" "lambda_package" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambda"
  output_path = "${path.module}/lambda/lambda.zip"
  excludes = [
    "layer.zip",
    "python/**",
    "tmp/**",
    "wheelhouse/**",
    "tests/**",
    "__pycache__/**",
    "build-layer.sh",
    "requirements.txt",
    "requirements-dev.txt",
    "pytest.ini",
    "run-integration-tests.sh",
    "testfile",
    ".pytest_cache/**",
    ".pytest_cache"
  ]
}

resource "aws_lambda_layer_version" "rag_layer" {
  layer_name               = "rag_layer"
  filename                 = "${path.module}/../../lambda/layer.zip"
  description              = "RAG layer"
  compatible_runtimes      = ["python3.13"]
  compatible_architectures = ["x86_64"]
}

resource "aws_lambda_function" "rag" {
  filename         = data.archive_file.lambda_package.output_path
  function_name    = local.lambda_name
  role             = aws_iam_role.lambda_execution_role.arn
  handler          = "src.handler.lambda_handler"
  source_code_hash = data.archive_file.lambda_package.output_base64sha256
  runtime          = "python3.13"
  architectures    = ["x86_64"]
  timeout          = 30

  layers = [
    aws_lambda_layer_version.rag_layer.arn
  ]

  environment {
    variables = local.lambda_environment
  }

  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_log_group
  ]
}

resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 3
}

resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.project}-${var.env}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_execution_policy" {
  name = "${var.project}-${var.env}-lambda-execution-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

resource "aws_lambda_permission" "allow_apigw_invoke" {
  statement_id  = "${var.project}-${var.env}-allow-apigw-invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rag.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.rag_api.execution_arn}/*/*"
}
