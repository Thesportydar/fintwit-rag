from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    s3_processed_bucket: str = "inaqui-prod-twitter-scraper"
    s3_processed_prefix: str = "processed"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_name: str = "tweets"
    jina_api_key: str = ""
    jina_embed_url: str = "https://api.jina.ai/v1/embeddings"
    jina_embed_model: str = "jina-embeddings-v5-text-nano"
    openai_api_key: str = ""
    enrichment_model: str = "gpt-4o-mini"
    enrichment_batch_size: int = 15
    aws_region: str = "us-east-1"

    @classmethod
    def from_env(cls) -> PipelineConfig:
        return cls(
            s3_processed_bucket=os.environ.get("S3_PROCESSED_BUCKET", cls.s3_processed_bucket),
            s3_processed_prefix=os.environ.get("S3_PROCESSED_PREFIX", cls.s3_processed_prefix),
            qdrant_url=os.environ.get("QDRANT_URL", cls.qdrant_url),
            qdrant_api_key=os.environ.get("QDRANT_API_KEY"),
            collection_name=os.environ.get("COLLECTION_NAME", cls.collection_name),
            jina_api_key=os.environ.get("JINA_API_KEY", ""),
            jina_embed_url=os.environ.get("JINA_EMBED_URL", cls.jina_embed_url),
            jina_embed_model=os.environ.get("JINA_EMBED_MODEL", cls.jina_embed_model),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            enrichment_model=os.environ.get("ENRICHMENT_MODEL", os.environ.get("OPENAI_MODEL", cls.enrichment_model)),
            enrichment_batch_size=int(os.environ.get("ENRICHMENT_BATCH_SIZE", cls.enrichment_batch_size)),
            aws_region=os.environ.get("AWS_REGION", cls.aws_region),
        )
