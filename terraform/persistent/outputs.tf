output "qdrant_ebs_volume_id" {
  value       = aws_ebs_volume.qdrant.id
  description = "The ID of the persistent EBS volume for Qdrant"
}

output "qdrant_ssm_parameter_name" {
  value       = aws_ssm_parameter.qdrant_volume_id.name
  description = "The SSM parameter name storing the volume ID"
}
