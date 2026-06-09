import json
import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import AppConfig
from .embeddings import JinaEmbeddingConfig, JinaEmbeddingProvider
from .llm import get_llm
from .vector_store import QdrantStoreConfig, QdrantTweetVectorStore, SearchResult, TweetFilters, TweetHit

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PROMPTS_DIR = Path(__file__).parent / "prompts"

with open(PROMPTS_DIR / "system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read().strip()

with open(PROMPTS_DIR / "user_prompt.txt", "r", encoding="utf-8") as f:
    USER_PROMPT_TEMPLATE = f.read().strip()


@dataclass(frozen=True)
class SearchRequest:
    query: str
    filters: TweetFilters
    retrieve_limit: int = 20
    top_n: int = 5

    @classmethod
    def from_body(cls, body: dict) -> "SearchRequest":
        if not isinstance(body, dict):
            raise ValueError("El body debe ser un objeto JSON")

        query = str(body.get("query", "")).strip()
        if not query:
            raise ValueError("El campo 'query' es requerido")

        try:
            retrieve_limit = int(body.get("retrieve_limit", 20))
            top_n = int(body.get("top_n", 5))
        except (TypeError, ValueError) as exc:
            raise ValueError("retrieve_limit y top_n deben ser números enteros") from exc

        if retrieve_limit < 1 or top_n < 1:
            raise ValueError("retrieve_limit y top_n deben ser mayores que 0")

        return cls(
            query=query,
            filters=TweetFilters.from_dict(body.get("filters")),
            retrieve_limit=retrieve_limit,
            top_n=top_n,
        )


app_config = AppConfig.from_env()
embedding_provider = JinaEmbeddingProvider(
    JinaEmbeddingConfig(
        api_key=app_config.jina_api_key,
        embed_url=app_config.jina_embed_url,
        rerank_url=app_config.jina_rerank_url,
        embed_model=app_config.jina_embed_model,
        rerank_model=app_config.jina_rerank_model,
    )
)
vector_store = QdrantTweetVectorStore(
    QdrantStoreConfig(
        url=app_config.qdrant_url,
        api_key=app_config.qdrant_api_key,
        collection_name=app_config.collection_name,
    )
)
llm = get_llm(app_config.llm_provider)


def format_context(points: list[TweetHit]) -> str:
    blocks = []
    for p in points:
        pl = p.payload
        timestamp = pl.get("tweet_timestamp") or ""
        date = timestamp[:10]
        handle = pl.get("user_handle", "")
        content = pl.get("content", "")
        blocks.append(
            "\n".join(
                [
                    "<<< TWEET >>>",
                    f"fecha: {date}",
                    f"autor: @{handle}",
                    f"contenido: {content}",
                    "<<< /TWEET >>>",
                ]
            )
        )
    return "\n\n".join(blocks)


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        search_request = SearchRequest.from_body(body)

        logger.info(
            "Query: '%s' | Filters: %s | retrieve=%s top_n=%s",
            search_request.query,
            search_request.filters,
            search_request.retrieve_limit,
            search_request.top_n,
        )

        query_vector = embedding_provider.embed_query(search_request.query)

        results: SearchResult = vector_store.query(
            query_vector=query_vector,
            limit=search_request.retrieve_limit,
            filters=search_request.filters,
        )

        if not results.points:
            return _response(200, {"answer": "No encontré tweets relevantes para tu consulta.", "sources": []})

        docs = [point.content for point in results.points]
        ranked_indices = embedding_provider.rerank(search_request.query, docs, top_n=search_request.top_n)
        top_points = [results.points[i] for i in ranked_indices]

        context_str = format_context(top_points)
        user_prompt = USER_PROMPT_TEMPLATE.format(context=context_str, query=search_request.query)
        answer = llm.complete(system=SYSTEM_PROMPT, user=user_prompt)

        sources = [
            {
                "url": p.payload.get("url"),
                "handle": p.payload.get("user_handle"),
                "date": p.payload.get("tweet_timestamp", "")[:10],
                "content": p.payload.get("content"),
            }
            for p in top_points
        ]

        return _response(200, {"answer": answer, "sources": sources})

    except ValueError as exc:
        return _response(400, {"error": str(exc)})

    except requests.RequestException as exc:
        logger.error("Jina API error: %s", str(exc))
        return _response(502, {"error": "Error de conexión o HTTP llamando a Jina API"})

    except Exception:
        logger.error("Unhandled error", exc_info=True)
        return _response(500, {"error": "Internal server error"})


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }
