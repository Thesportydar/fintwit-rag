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
