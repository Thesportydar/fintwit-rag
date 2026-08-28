locals {
  lambda_ingest_name = "${var.project}-${var.env}-ingest"

  lambda_ingest_environment = {
    COLLECTION_NAME     = var.collection_name
    QDRANT_URL          = "http://${trimsuffix(aws_route53_record.www.fqdn, ".")}:6333"
    QDRANT_API_KEY      = var.qdrant_api_key
    JINA_API_KEY        = var.jina_api_key
    JINA_EMBED_URL      = var.jina_embed_url
    JINA_EMBED_MODEL    = var.jina_embed_model
    OPENAI_API_KEY      = var.openai_api_key
    ENRICHMENT_MODEL    = var.enrichment_model
    S3_PROCESSED_BUCKET = var.s3_processed_bucket
    S3_PROCESSED_PREFIX = var.s3_processed_prefix
  }
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
