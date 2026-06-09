from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    jina_api_key: str
    qdrant_url: str
    qdrant_api_key: str | None
    collection_name: str = "tweets"
    llm_provider: str = "openai"
    jina_embed_url: str = "https://api.jina.ai/v1/embeddings"
    jina_rerank_url: str = "https://api.jina.ai/v1/rerank"
    jina_embed_model: str = "jina-embeddings-v5-text-nano"
    jina_rerank_model: str = "jina-reranker-v3"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            jina_api_key=os.environ["JINA_API_KEY"],
            qdrant_url=os.environ["QDRANT_URL"],
            qdrant_api_key=os.environ.get("QDRANT_API_KEY"),
            collection_name=os.environ.get("COLLECTION_NAME", "tweets"),
            llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
            jina_embed_url=os.environ.get("JINA_EMBED_URL", cls.jina_embed_url),
            jina_rerank_url=os.environ.get("JINA_RERANK_URL", cls.jina_rerank_url),
            jina_embed_model=os.environ.get("JINA_EMBED_MODEL", cls.jina_embed_model),
            jina_rerank_model=os.environ.get("JINA_RERANK_MODEL", cls.jina_rerank_model),
        )
