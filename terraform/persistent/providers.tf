provider "aws" {
  region  = var.region
  profile = var.profile

  assume_role {
    role_arn = var.terraform_role_arn
  }

  default_tags {
    tags = {
      ManagedBy   = "Terraform"
      Environment = var.env
      Project     = var.project
    }
  }
}

provider "aws" {
  alias   = "route53"
  region  = var.region
  profile = var.profile

  assume_role {
    role_arn = var.route53_role_arn
  }

  default_tags {
    tags = {
      ManagedBy   = "Terraform"
      Environment = var.env
      Project     = var.project
    }
  }
}
