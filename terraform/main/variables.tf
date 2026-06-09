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

variable "bedrock_model_id" {
  description = "AWS Bedrock model id"
  type        = string
  default     = "anthropic.claude-3-5-haiku-20241022-v1:0"
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
