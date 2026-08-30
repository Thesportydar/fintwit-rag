variable "env" {
  description = "The deployment environment (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project" {
  description = "The name of the project"
  type        = string
}

variable "terraform_role_arn" {
  description = "The ARN of the role to assume for Terraform execution"
  type        = string
}

variable "region" {
  description = "The AWS region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "profile" {
  description = "The AWS CLI profile to use for authentication"
  type        = string
  default     = "default"
}

variable "availability_zone" {
  description = "The Availability Zone to deploy the EC2 instance and EBS volume"
  type        = string
  default     = "us-east-1a"
}

variable "jina_api_key" {
  description = "API key for Jina embeddings and reranking"
  type        = string
  sensitive   = true
}

variable "qdrant_api_key" {
  description = "API key for Qdrant"
  type        = string
  sensitive   = true
  default     = ""
}

variable "collection_name" {
  description = "Qdrant collection name"
  type        = string
}

variable "llm_provider" {
  description = "LLM provider used by the Lambda"
  type        = string
  default     = "openai"
}

variable "openai_api_key" {
  description = "API key for OpenAI"
  type        = string
  sensitive   = true
}

variable "openai_model" {
  description = "OpenAI model name"
  type        = string
  default     = "gpt-4o-mini"
}

variable "enrichment_model" {
  description = "OpenAI model name for tweet enrichment in pipeline lambda"
  type        = string
  default     = "gpt-4o-mini"
}

variable "bedrock_model_id" {
  description = "AWS Bedrock model id"
  type        = string
  default     = "anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "dynamodb_checkpoint_table" {
  description = "Name of the DynamoDB table for LangGraph checkpoints"
  type        = string
  default     = "fintwit-checkpoints"
}

variable "dynamodb_store_table" {
  description = "Name of the DynamoDB table for LangGraph store"
  type        = string
  default     = "fintwit-store"
}

variable "dynamodb_rate_limit_table" {
  description = "Name of the DynamoDB table for distributed rate limiting"
  type        = string
  default     = "fintwit-rate-limits"
}


variable "jina_embed_url" {
  description = "Jina embeddings endpoint"
  type        = string
  default     = "https://api.jina.ai/v1/embeddings"
}

variable "jina_rerank_url" {
  description = "Jina rerank endpoint"
  type        = string
  default     = "https://api.jina.ai/v1/rerank"
}

variable "jina_embed_model" {
  description = "Jina embeddings model"
  type        = string
  default     = "jina-embeddings-v5-text-nano"
}

variable "jina_rerank_model" {
  description = "Jina reranker model"
  type        = string
  default     = "jina-reranker-v3"
}

variable "qdrant_domain_name" {
  description = "The domain name for the Qdrant instance"
  type        = string
}

variable "hosted_zone_name" {
  description = "The name of the Route 53 hosted zone"
  type        = string
}

variable "route53_role_arn" {
  description = "The ARN of the role to assume for Route53 management in the management account"
  type        = string
}


variable "langsmith_api_key" {
  description = "API key for LangSmith tracing"
  type        = string
  sensitive   = true
  default     = ""
}

variable "langsmith_project" {
  description = "Project name for LangSmith tracing"
  type        = string
  default     = "fintwit-rag"
}

variable "s3_processed_bucket" {
  description = "Bucket S3 donde el scraper guarda tweets y la pipeline escribe Parquets"
  type        = string
  default     = "inaqui-prod-twitter-scraper"
}

variable "s3_processed_prefix" {
  description = "Prefijo/carpeta dentro del bucket S3 para datos procesados"
  type        = string
  default     = "processed"
}

variable "cognito_demo_password" {
  description = "Contraseña inicial para el usuario demo de Cognito"
  type        = string
  sensitive   = true
  default     = "FinTwit2026!"
}

variable "cognito_admin_email" {
  description = "Email del usuario administrador para desarrollo local"
  type        = string
  default     = "admin@fintwit.com"
}

variable "cognito_admin_password" {
  description = "Contraseña para el usuario administrador de Cognito"
  type        = string
  sensitive   = true
  default     = "FinTwitAdmin2026!"
}

variable "retriever_k" {
  description = "Number of documents to retrieve before reranking"
  type        = number
  default     = 50
}

variable "reranker_top_n" {
  description = "Number of top documents to keep after reranking"
  type        = number
  default     = 5
}

variable "crag_max_attempts" {
  description = "Maximum CRAG search attempts"
  type        = number
  default     = 2
}

variable "crag_relevance_threshold" {
  description = "Relevance threshold score (0-10) for CRAG evaluation"
  type        = number
  default     = 5.0
}

variable "memory_token_limit" {
  description = "Token limit before triggering summarization"
  type        = number
  default     = 4000
}

variable "memory_keep_messages" {
  description = "Number of recent messages to keep uncompressed"
  type        = number
  default     = 10
}

variable "rate_limit_requests" {
  description = "Maximum requests allowed per rate limit window"
  type        = number
  default     = 60
}

variable "rate_limit_window_seconds" {
  description = "Rate limit sliding window in seconds"
  type        = number
  default     = 1800
}

variable "max_input_chars" {
  description = "Maximum characters allowed per user input message"
  type        = number
  default     = 1000
}

variable "max_thread_turns" {
  description = "Maximum user messages allowed per conversation thread"
  type        = number
  default     = 20
}

variable "invocation_timeout_seconds" {
  description = "Execution timeout for Bedrock AgentCore invocations in seconds"
  type        = number
  default     = 45
}

variable "allowed_origins" {
  description = "Comma-separated allowed CORS origins"
  type        = string
  default     = "https://rag.fintwit.com.ar,http://localhost:5173,http://localhost:3000"
}

variable "budget_limit_amount" {
  description = "Monthly budget limit in USD"
  type        = string
  default     = "25"
}

variable "budget_subscriber_emails" {
  description = "List of email addresses to receive AWS budget notifications"
  type        = list(string)
  default     = ["ipaladinobravo@gmail.com"]
}
