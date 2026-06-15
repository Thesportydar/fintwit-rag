import os
from dataclasses import dataclass


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
    dynamodb_checkpoint_table: str = "fintwit-checkpoints"
    dynamodb_store_table: str = "fintwit-store"

    # LLM Settings
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # Retrieval Settings
    retriever_k: int = 50
    reranker_top_n: int = 5

    # Middleware Settings
    memory_token_limit: int = 4000
    memory_keep_messages: int = 10

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
            dynamodb_checkpoint_table=os.environ.get("DYNAMODB_CHECKPOINT_TABLE", cls.dynamodb_checkpoint_table),
            dynamodb_store_table=os.environ.get("DYNAMODB_STORE_TABLE", cls.dynamodb_store_table),
            llm_temperature=float(os.environ.get("LLM_TEMPERATURE", cls.llm_temperature)),
            llm_max_tokens=int(os.environ.get("LLM_MAX_TOKENS", cls.llm_max_tokens)),
            retriever_k=int(os.environ.get("RETRIEVER_K", cls.retriever_k)),
            reranker_top_n=int(os.environ.get("RERANKER_TOP_N", cls.reranker_top_n)),
            memory_token_limit=int(os.environ.get("MEMORY_TOKEN_LIMIT", cls.memory_token_limit)),
            memory_keep_messages=int(os.environ.get("MEMORY_KEEP_MESSAGES", cls.memory_keep_messages)),
        )
