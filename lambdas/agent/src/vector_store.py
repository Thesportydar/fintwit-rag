from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor
from langchain_core.embeddings import Embeddings
from langchain_core.tools import tool
from qdrant_client import QdrantClient, models
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, Range


@dataclass(frozen=True)
class TweetFilters:
    start_date: str | None = None
    end_date: str | None = None
    user_handles: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    sentiment: str | None = None
    topics: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TweetFilters:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("filters debe ser un objeto JSON")

        handles = data.get("user_handles", [])
        if isinstance(handles, str):
            handles = [handles]
        elif handles is None:
            handles = []

        tickers = data.get("tickers", [])
        if isinstance(tickers, str):
            tickers = [tickers]
        elif tickers is None:
            tickers = []

        topics = data.get("topics", [])
        if isinstance(topics, str):
            topics = [topics]
        elif topics is None:
            topics = []

        try:
            return cls(
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                user_handles=list(handles),
                tickers=list(tickers),
                sentiment=data.get("sentiment"),
                topics=list(topics),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("filters tiene valores inválidos") from exc

    def to_qdrant_filter(self) -> Filter | None:
        conditions = []
        if self.user_handles:
            if len(self.user_handles) > 1:
                conditions.append(FieldCondition(key="metadata.user_handle", match=MatchAny(any=self.user_handles)))
            else:
                conditions.append(
                    FieldCondition(key="metadata.user_handle", match=MatchValue(value=self.user_handles[0]))
                )

        if self.start_date or self.end_date:
            gte_year = int(self.start_date[:4]) if self.start_date and len(self.start_date) >= 4 else None
            lte_year = int(self.end_date[:4]) if self.end_date and len(self.end_date) >= 4 else None
            if gte_year or lte_year:
                conditions.append(FieldCondition(key="metadata.tweet_year", range=Range(gte=gte_year, lte=lte_year)))

        return Filter(must=conditions) if conditions else None


def hybrid_search_tweets(
    client: QdrantClient,
    collection_name: str,
    query: str,
    embeddings: Embeddings,
    qdrant_filter: Filter | None = None,
    limit: int = 50,
) -> list[Document]:
    """
    Ejecuta búsqueda híbrida nativa en Qdrant combinando:
    - Dense Vectors (Jina Embeddings) usando named vector 'dense'
    - Sparse BM25 Vectors (Server-side inference con 'Qdrant/bm25') usando 'bm25'
    - Fusión nativa con Reciprocal Rank Fusion (RRF).
    """
    dense_vector = embeddings.embed_query(query)

    prefetch = [
        models.Prefetch(
            query=dense_vector,
            filter=qdrant_filter,
            limit=limit,
        ),
        models.Prefetch(
            query=models.Document(
                text=query,
                model="Qdrant/bm25",
            ),
            using="bm25",
            filter=qdrant_filter,
            limit=limit,
        ),
    ]

    response = client.query_points(
        collection_name=collection_name,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=limit,
    )

    docs = []
    for point in response.points:
        payload = point.payload or {}
        content = payload.get("content", "")
        meta = payload.get("metadata", {})
        docs.append(Document(page_content=content, metadata=meta))

    return docs


def format_tweet_doc(d: Document) -> str:
    meta = d.metadata or {}
    handle = meta.get("user_handle", "unknown")
    timestamp = meta.get("tweet_timestamp", "")
    date = timestamp[:10] if timestamp else "unknown"
    return f"<<< TWEET >>>\nautor: @{handle}\nfecha: {date}\ncontenido: {d.page_content}\n<<< /TWEET >>>"


def create_search_tweets_tool(
    qdrant_client: QdrantClient,
    collection_name: str,
    embeddings: Embeddings,
    compressor: BaseDocumentCompressor | None = None,
    limit: int = 50,
):
    """Crea la herramienta @tool ejecutable conectada a Qdrant y Jina Reranker."""
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @tool
    def search_tweets(
        query: str,
        start_date: str | None = None,
        end_date: str | None = None,
        user_handles: list[str] | None = None,
        tickers: list[str] | None = None,
        sentiment: str | None = None,
        topics: list[str] | None = None,
    ) -> str:
        """Busca tweets financieros en la base de datos de fintwit usando búsqueda híbrida
        (Dense + BM25 server-side inference + RRF) y Re-ranking contextual con Jina.

        Args:
            query: Frase en lenguaje natural que describa el contenido buscado.
            start_date: Fecha de inicio en formato YYYY-MM-DD. Opcional.
            end_date: Fecha de fin en formato YYYY-MM-DD. Opcional.
            user_handles: Lista de usuarios a filtrar. Usar SOLO si el usuario mencionó una cuenta específica por su @handle exacto.
            tickers: Lista de tickers específicos a filtrar (ej: ['GGAL', 'AL30', 'BTC']). Opcional.
            sentiment: Filtrar por sentimiento específico ('bullish', 'bearish', 'neutral'). Opcional.
            topics: Lista de tópicos específicos a filtrar (ej: ['acciones_locales', 'deuda_soberana', 'fx_dolar']). Opcional.
        """
        if start_date and not date_pattern.match(start_date):
            return f"Error de validación: start_date '{start_date}' no tiene el formato correcto YYYY-MM-DD."
        if end_date and not date_pattern.match(end_date):
            return f"Error de validación: end_date '{end_date}' no tiene el formato correcto YYYY-MM-DD."

        clean_handles = [h.lstrip("@") for h in (user_handles or [])]

        filters = TweetFilters(
            start_date=start_date,
            end_date=end_date,
            user_handles=clean_handles,
            tickers=tickers or [],
            sentiment=sentiment,
            topics=topics or [],
        )
        qdrant_filter = filters.to_qdrant_filter()

        effective_query = query
        if tickers:
            missing_tickers = [t for t in tickers if t.lower() not in effective_query.lower()]
            if missing_tickers:
                effective_query = f"{effective_query} {' '.join(missing_tickers)}"

        docs = hybrid_search_tweets(
            client=qdrant_client,
            collection_name=collection_name,
            query=effective_query,
            embeddings=embeddings,
            qdrant_filter=qdrant_filter,
            limit=limit,
        )

        if not docs:
            return "No se encontraron tweets relevantes para la búsqueda solicitada."

        if compressor:
            docs = list(compressor.compress_documents(docs, effective_query))

        return "\n\n".join(format_tweet_doc(d) for d in docs)

    return search_tweets
