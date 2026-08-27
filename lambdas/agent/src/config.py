import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    jina_api_key: str
    qdrant_url: str
    qdrant_api_key: str | None
    collection_name: str = "tweets"
    llm_provider: str = "openai"
    openai_model: str = "gpt-4o-mini"
    bedrock_model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0"
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

    # CRAG Settings
    crag_max_attempts: int = 2
    crag_relevance_threshold: float = 5.0

    # Memory / Summarization Settings
    memory_token_limit: int = 4000
    memory_keep_messages: int = 10

    # Observability
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "fintwit-rag"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            jina_api_key=os.environ["JINA_API_KEY"],
            qdrant_url=os.environ["QDRANT_URL"],
            qdrant_api_key=os.environ.get("QDRANT_API_KEY"),
            collection_name=os.environ.get("COLLECTION_NAME", "tweets"),
            llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
            openai_model=os.environ.get("OPENAI_MODEL", cls.openai_model),
            bedrock_model_id=os.environ.get("BEDROCK_MODEL_ID", cls.bedrock_model_id),
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
            crag_max_attempts=int(os.environ.get("CRAG_MAX_ATTEMPTS", cls.crag_max_attempts)),
            crag_relevance_threshold=float(os.environ.get("CRAG_RELEVANCE_THRESHOLD", cls.crag_relevance_threshold)),
            memory_token_limit=int(os.environ.get("MEMORY_TOKEN_LIMIT", cls.memory_token_limit)),
            memory_keep_messages=int(os.environ.get("MEMORY_KEEP_MESSAGES", cls.memory_keep_messages)),
            langsmith_tracing=os.environ.get("LANGSMITH_TRACING", "false").lower() in ("true", "1"),
            langsmith_api_key=os.environ.get("LANGSMITH_API_KEY"),
            langsmith_project=os.environ.get("LANGSMITH_PROJECT", cls.langsmith_project),
        )
