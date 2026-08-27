output "qdrant_snapshot_id" {
  value       = nonsensitive(aws_ssm_parameter.qdrant_snapshot_id.value)
  description = "The snapshot ID configured for Qdrant data"
}

output "qdrant_ssm_parameter_name" {
  value       = aws_ssm_parameter.qdrant_snapshot_id.name
  description = "The SSM parameter name storing the snapshot ID"
}

output "dynamodb_checkpoint_table_arn" {
  value       = aws_dynamodb_table.checkpoints.arn
  description = "ARN of the LangGraph checkpoint DynamoDB table"
}

output "dynamodb_store_table_arn" {
  value       = aws_dynamodb_table.store.arn
  description = "ARN of the LangGraph store DynamoDB table"
}

output "frontend_bucket_name" {
  value       = aws_s3_bucket.frontend.id
  description = "The name of the S3 bucket hosting the frontend site"
}

output "cloudfront_distribution_id" {
  value       = aws_cloudfront_distribution.s3_distribution.id
  description = "The ID of the CloudFront distribution"
}

output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.s3_distribution.domain_name
  description = "The cloudfront.net domain name"
}

output "frontend_url" {
  value       = "https://${aws_route53_record.www.name}"
  description = "The public URL of the frontend"
}
