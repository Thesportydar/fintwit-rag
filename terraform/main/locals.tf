locals {
  api_name    = "${var.project}-${var.env}-api"
  lambda_name = "${var.project}-${var.env}-rag"
  lambda_environment = {
    COLLECTION_NAME   = var.collection_name
    LLM_PROVIDER      = var.llm_provider
    JINA_API_KEY      = var.jina_api_key
    JINA_EMBED_URL    = var.jina_embed_url
    JINA_RERANK_URL   = var.jina_rerank_url
    JINA_EMBED_MODEL  = var.jina_embed_model
    JINA_RERANK_MODEL = var.jina_rerank_model
    QDRANT_URL        = "http://${trimsuffix(aws_route53_record.www.fqdn, ".")}:6333"
    QDRANT_API_KEY    = var.qdrant_api_key
    OPENAI_API_KEY    = var.openai_api_key
    OPENAI_MODEL      = var.openai_model
    BEDROCK_MODEL_ID  = var.bedrock_model_id
  }
}
