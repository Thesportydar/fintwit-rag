terraform {
  backend "s3" {
    key = "fintwit-rag/terraform.tfstate"
  }
}
