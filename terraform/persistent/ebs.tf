resource "aws_ebs_volume" "qdrant" {
  availability_zone = var.availability_zone
  size              = 30
  type              = "gp3"

  tags = {
    Name = "${var.project}-${var.env}-qdrant-data"
  }
}

resource "aws_ssm_parameter" "qdrant_volume_id" {
  name        = "/${var.project}/${var.env}/qdrant_volume_id"
  description = "ID of the persistent EBS volume for Qdrant"
  type        = "String"
  value       = aws_ebs_volume.qdrant.id
}
