output "lambda_pipeline_layer_arn" {
  value       = aws_lambda_layer_version.pipeline_layer.arn
  description = "ARN of the Ingest Pipeline Lambda Layer"
}

output "lambda_ingest_name" {
  value       = aws_lambda_function.ingest.function_name
  description = "Name of the Ingest Pipeline Lambda function"
}

output "lambda_ingest_arn" {
  value       = aws_lambda_function.ingest.arn
  description = "ARN of the Ingest Pipeline Lambda function"
}

output "qdrant_instance_id" {
  value       = aws_instance.qdrant.id
  description = "The EC2 Instance ID for Qdrant (use for SSM Session Manager)"
}

output "qdrant_public_ip" {
  value       = aws_eip.lb.public_ip
  description = "The Elastic IP of the Qdrant instance"
}

output "qdrant_dashboard_url" {
  value       = "http://${var.qdrant_domain_name}:6333/dashboard"
  description = "The Qdrant Web Dashboard URL"
}

output "qdrant_ebs_volume_id" {
  value       = aws_ebs_volume.qdrant.id
  description = "The ID of the active EBS volume created for Qdrant"
}

output "agent_ecr_repository_url" {
  value       = aws_ecr_repository.agent.repository_url
  description = "The ECR Repository URL for the FinTwit Agent container"
}

output "agentcore_runtime_id" {
  value       = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_id
  description = "The Bedrock AgentCore Agent Runtime ID"
}

output "agentcore_runtime_arn" {
  value       = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
  description = "The Bedrock AgentCore Agent Runtime ARN"
}

output "cognito_user_pool_id" {
  value       = aws_cognito_user_pool.pool.id
  description = "ID of the Amazon Cognito User Pool"
}

output "cognito_client_id" {
  value       = aws_cognito_user_pool_client.client.id
  description = "ID of the Amazon Cognito User Pool Client (Public SPA)"
}

output "cognito_discovery_url" {
  value       = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.pool.id}/.well-known/openid-configuration"
  description = "OIDC Discovery URL for the Cognito User Pool"
}

output "cognito_demo_email" {
  value       = "demo@fintwit.com"
  description = "Initial demo user email for testing and portfolio access"
}

output "cognito_admin_email" {
  value       = var.cognito_admin_email
  description = "Admin user email for local development with unlimited rate limit"
}

output "budget_name" {
  value       = aws_budgets_budget.monthly.name
  description = "Name of the monthly AWS Cost Budget"
}
