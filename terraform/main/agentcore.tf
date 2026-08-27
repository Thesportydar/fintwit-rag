# ============================================================================
# AWS ECR Repository for AgentCore Container Image
# ============================================================================

resource "aws_ecr_repository" "agent" {
  name                 = "${var.project}-${var.env}-agent"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project}-${var.env}-agent-ecr"
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Delete untagged images older than 3 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}


# ============================================================================
# IAM Role and Policies for Bedrock AgentCore Runtime
# ============================================================================

resource "aws_iam_role" "agentcore_runtime_role" {
  name = "${var.project}-${var.env}-agentcore-runtime-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock-agentcore.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "agentcore_runtime_policy" {
  name = "${var.project}-${var.env}-agentcore-runtime-policy"
  role = aws_iam_role.agentcore_runtime_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs & Metrics
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # X-Ray Tracing
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      },
      # Bedrock Models
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      },
      # ECR Image Pull
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = aws_ecr_repository.agent.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      # DynamoDB Checkpoint & Store Tables
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
          "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_checkpoint_table}/*",
          "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_store_table}",
          "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_store_table}/*"
        ]
      }
    ]
  })
}

# ============================================================================
# Bedrock AgentCore Agent Runtime Resource
# ============================================================================

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = replace("${var.project}_${var.env}_agent", "-", "_")
  description        = "FinTwit LangGraph RAG Agent Runtime"
  role_arn           = aws_iam_role.agentcore_runtime_role.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent.repository_url}:latest"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "AGUI"
  }

  environment_variables = {
    JINA_API_KEY              = var.jina_api_key
    QDRANT_URL                = "http://${var.qdrant_domain_name}:6333"
    QDRANT_API_KEY            = var.qdrant_api_key
    COLLECTION_NAME           = var.collection_name
    LLM_PROVIDER              = var.llm_provider
    OPENAI_API_KEY            = var.openai_api_key
    OPENAI_MODEL              = var.openai_model
    BEDROCK_MODEL_ID          = var.bedrock_model_id
    JINA_EMBED_URL            = var.jina_embed_url
    JINA_RERANK_URL           = var.jina_rerank_url
    JINA_EMBED_MODEL          = var.jina_embed_model
    JINA_RERANK_MODEL         = var.jina_rerank_model
    DYNAMODB_CHECKPOINT_TABLE = var.dynamodb_checkpoint_table
    DYNAMODB_STORE_TABLE      = var.dynamodb_store_table
    RETRIEVER_K               = "5"
    RERANKER_TOP_N            = "3"
    CRAG_MAX_ATTEMPTS         = "2"
    CRAG_RELEVANCE_THRESHOLD  = "0.6"
    MEMORY_TOKEN_LIMIT        = "3000"
    MEMORY_KEEP_MESSAGES      = "6"
    LANGSMITH_TRACING         = var.langsmith_api_key != "" ? "true" : "false"
    LANGSMITH_API_KEY         = var.langsmith_api_key
    LANGSMITH_PROJECT         = var.langsmith_project
  }

  depends_on = [
    aws_iam_role_policy.agentcore_runtime_policy,
    aws_ecr_repository.agent
  ]
}
