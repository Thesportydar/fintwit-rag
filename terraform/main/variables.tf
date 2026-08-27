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

variable "apigw_domain_name" {
  description = "The domain name for the HTTP API Gateway"
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
