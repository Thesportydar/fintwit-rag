resource "aws_ssm_parameter" "qdrant_snapshot_id" {
  name        = "/${var.project}/${var.env}/qdrant_snapshot_id"
  description = "Snapshot ID of the persistent Qdrant data"
  type        = "String"
  value       = var.qdrant_snapshot_id
}
