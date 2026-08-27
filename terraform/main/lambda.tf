# --- Agent Lambda Package ---
data "archive_file" "agent_package" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/agent"
  output_path = "${path.module}/build/agent.zip"
  excludes = [
    "tests/**",
    "__pycache__/**",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
    ".venv/**",
    "venv/**",
    "env/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".DS_Store",
    ".env*",
    ".dockerignore"
  ]
}

# --- Pipeline Ingestion Lambda Package ---
data "archive_file" "pipeline_package" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/pipeline"
  output_path = "${path.module}/build/pipeline.zip"
  excludes = [
    "tests/**",
    "__pycache__/**",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
    ".venv/**",
    "venv/**",
    "env/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".DS_Store",
    ".env*",
    ".dockerignore"
  ]
}

# --- 1. Agent Dependency Layer ---
resource "aws_lambda_layer_version" "agent_layer" {
  layer_name               = "${var.project}-${var.env}-agent-layer"
  filename                 = "${path.module}/../../lambdas/agent_layer.zip"
  source_code_hash         = filebase64sha256("${path.module}/../../lambdas/agent_layer.zip")
  description              = "FinTwit Agent dependencies layer (LangGraph, LangChain, Qdrant, OpenAI)"
  compatible_runtimes      = ["python3.13"]
  compatible_architectures = ["arm64"]
}

# --- 2. Pipeline Dependency Layer ---
resource "aws_lambda_layer_version" "pipeline_layer" {
  layer_name               = "${var.project}-${var.env}-pipeline-layer"
  filename                 = "${path.module}/../../lambdas/pipeline_layer.zip"
  source_code_hash         = filebase64sha256("${path.module}/../../lambdas/pipeline_layer.zip")
  description              = "FinTwit Ingestion Pipeline dependencies layer (PyArrow, Qdrant, OpenAI)"
  compatible_runtimes      = ["python3.13"]
  compatible_architectures = ["arm64"]
}

# --- 1. Agent Query API Lambda ---
resource "aws_lambda_function" "rag" {
  filename         = data.archive_file.agent_package.output_path
  function_name    = local.lambda_name
  role             = aws_iam_role.lambda_execution_role.arn
  handler          = "src.handler.lambda_handler"
  source_code_hash = data.archive_file.agent_package.output_base64sha256
  runtime          = "python3.13"
  architectures    = ["arm64"]
  timeout          = 90
  memory_size      = 512

  layers = [
    aws_lambda_layer_version.agent_layer.arn
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

# --- 2. Ingest & Enrichment Event-Driven Lambda ---
resource "aws_lambda_function" "ingest" {
  filename         = data.archive_file.pipeline_package.output_path
  function_name    = local.lambda_ingest_name
  role             = aws_iam_role.lambda_execution_role.arn
  handler          = "src.handler.lambda_handler"
  source_code_hash = data.archive_file.pipeline_package.output_base64sha256
  runtime          = "python3.13"
  architectures    = ["arm64"]
  timeout          = 180
  memory_size      = 512

  layers = [
    aws_lambda_layer_version.pipeline_layer.arn
  ]

  environment {
    variables = local.lambda_ingest_environment
  }

  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_ingest_log_group
  ]
}

resource "aws_cloudwatch_log_group" "lambda_ingest_log_group" {
  name              = "/aws/lambda/${local.lambda_ingest_name}"
  retention_in_days = 3
}

# --- EventBridge Rule & Target for Ingestion ---
resource "aws_cloudwatch_event_rule" "tweets_uploaded" {
  name        = "${var.project}-${var.env}-tweets-uploaded"
  description = "Dispara el pipeline de ingesta y enriquecimiento cuando el scraper sube tweets"

  event_pattern = jsonencode({
    source      = ["twitter.scraper"]
    detail-type = ["tweetsuploaded"]
  })
}

resource "aws_cloudwatch_event_target" "ingest_lambda" {
  rule      = aws_cloudwatch_event_rule.tweets_uploaded.name
  target_id = "IngestLambdaTarget"
  arn       = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "allow_eventbridge_ingest" {
  statement_id  = "${var.project}-${var.env}-allow-eventbridge-ingest"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.tweets_uploaded.arn
}

# --- IAM Role & Policies ---
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
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_checkpoint_table}",
          "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_store_table}"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_processed_bucket}",
          "arn:aws:s3:::${var.s3_processed_bucket}/*"
        ]
      }
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
