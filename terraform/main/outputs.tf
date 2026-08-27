output "api_id" {
  value = aws_apigatewayv2_api.rag_api.id
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.rag_api.api_endpoint
}

output "query_endpoint" {
  value = "${aws_apigatewayv2_api.rag_api.api_endpoint}/query"
}

output "lambda_name" {
  value = aws_lambda_function.rag.function_name
}

output "lambda_arn" {
  value = aws_lambda_function.rag.arn
}

output "lambda_agent_layer_arn" {
  value       = aws_lambda_layer_version.agent_layer.arn
  description = "ARN of the Agent Lambda Layer"
}

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

output "api_custom_domain_endpoint" {
  value       = "https://${var.apigw_domain_name}/query"
  description = "The custom HTTPS domain endpoint for the API"
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
