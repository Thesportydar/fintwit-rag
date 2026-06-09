data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_ssm_parameter" "qdrant_volume_id" {
  name = "/${var.project}/${var.env}/qdrant_volume_id"
}

data "aws_ebs_volume" "qdrant" {
  filter {
    name   = "volume-id"
    values = [data.aws_ssm_parameter.qdrant_volume_id.value]
  }
}

resource "aws_instance" "qdrant" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  availability_zone           = data.aws_ebs_volume.qdrant.availability_zone
  iam_instance_profile        = aws_iam_instance_profile.qdrant_profile.name
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/../../ec2/user_data.sh", {
    qdrant_api_key = var.qdrant_api_key
  })
  vpc_security_group_ids = [aws_security_group.qdrant.id]
}

resource "aws_security_group" "qdrant" {
  name        = "${var.project}-${var.env}-qdrant-sg"
  description = "Security Group for Qdrant vector database"

  # NOTE: Para prod, la instancia deberia ser privada y el trafico deberia ir por la VPC
  # (Lambda in VPC con NAT Gateway) o estar detras de un ALB con terminacion HTTPS.
  ingress {
    description = "Allow Qdrant traffic"
    from_port   = 6333
    to_port     = 6333
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

resource "aws_volume_attachment" "qdrant" {
  device_name = "/dev/sdf"
  volume_id   = data.aws_ssm_parameter.qdrant_volume_id.value
  instance_id = aws_instance.qdrant.id
}

resource "aws_eip" "lb" {
  instance = aws_instance.qdrant.id
  domain   = "vpc"
}

resource "aws_iam_role" "qdrant_ec2_role" {
  name = "${var.project}-${var.env}-qdrant-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "qdrant_ssm" {
  role       = aws_iam_role.qdrant_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "qdrant_profile" {
  name = "${var.project}-${var.env}-qdrant-instance-profile"
  role = aws_iam_role.qdrant_ec2_role.name
}
