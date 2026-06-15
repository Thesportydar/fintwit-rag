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
  description = "The Availability Zone to deploy the EBS volume"
  type        = string
  default     = "us-east-1a"
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

variable "frontend_domain" {
  description = "The custom domain for the frontend (e.g., www.example.com)"
  type        = string
}

variable "s3_bucket_name" {
  description = "The name of the S3 bucket for frontend hosting"
  type        = string
}

variable "hosted_zone_name" {
  description = "The Route53 hosted zone name (e.g. example.com)"
  type        = string
}

variable "route53_role_arn" {
  description = "The ARN of the role to assume for Route53 operations"
  type        = string
}
