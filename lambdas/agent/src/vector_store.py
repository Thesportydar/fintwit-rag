from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Any

from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor
from langchain_core.embeddings import Embeddings
from langchain_core.tools import tool
from qdrant_client import QdrantClient, models
from qdrant_client.models import DatetimeRange, FieldCondition, Filter, MatchAny, MatchValue


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

        def as_list(value: Any) -> list[Any]:
            return [value] if isinstance(value, str) else list(value or [])

        try:
            return cls(
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                user_handles=as_list(data.get("user_handles")),
                tickers=as_list(data.get("tickers")),
                sentiment=data.get("sentiment"),
                topics=as_list(data.get("topics")),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("filters tiene valores inválidos") from exc

    def to_qdrant_filter(self) -> Filter | None:
        conditions = []
        if self.user_handles:
            conditions.append(FieldCondition(key="metadata.user_handle", match=MatchAny(any=self.user_handles)))

        conditions.extend(_date_range_conditions(self.start_date, self.end_date))

        for key, values in (("metadata.tickers", self.tickers), ("metadata.topics", self.topics)):
            if values:
                conditions.append(FieldCondition(key=key, match=MatchAny(any=values)))

        if self.sentiment:
            conditions.append(FieldCondition(key="metadata.sentiment", match=MatchValue(value=self.sentiment)))

        return Filter(must=conditions) if conditions else None


def _date_range_conditions(start_date: str | None, end_date: str | None) -> list[Filter]:
    """Convierte un rango inclusivo en una condición datetime sobre la fecha del tweet."""
    if not start_date and not end_date:
        return []

    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    if start and end and start > end:
        raise ValueError("start_date no puede ser posterior a end_date")

    lower_bound = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc) if start else None
    upper_bound = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) if end else None
    return [
        Filter(
            must=[
                FieldCondition(
                    key="metadata.tweet_timestamp",
                    range=DatetimeRange(gte=lower_bound, lt=upper_bound),
                )
            ]
        )
    ]


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
    for rank, point in enumerate(response.points, start=1):
        payload = point.payload or {}
        content = payload.get("content", "")
        meta = dict(payload.get("metadata", {}))
        meta.setdefault("evidence_id", f"qdrant:{point.id}")
        meta["retrieval_channel"] = "hybrid_rrf"
        meta["retrieval_rank"] = rank
        if isinstance(getattr(point, "score", None), int | float):
            meta["rrf_score"] = point.score
        docs.append(Document(page_content=content, metadata=meta))

    return docs


def format_tweet_doc(d: Document) -> str:
    meta = d.metadata or {}
    evidence_id = escape(str(meta.get("evidence_id", "unknown")), quote=True)
    handle = meta.get("user_handle", "unknown")
    timestamp = meta.get("tweet_timestamp", "")
    date = timestamp[:10] if timestamp else "unknown"
    url = escape(str(meta.get("url", "")), quote=True)
    safe_handle = escape(f"@{handle}", quote=True)
    safe_date = escape(str(date), quote=True)
    sentiment = escape(str(meta.get("sentiment", "")), quote=True)
    safe_content = escape(d.page_content)
    url_attribute = f' url="{url}"' if url else ""
    sentiment_attribute = f' sentiment="{sentiment}"' if sentiment else ""
    return (
        f'<tweet author="{safe_handle}" date="{safe_date}" id="{evidence_id}"'
        f"{sentiment_attribute}{url_attribute}>{safe_content}</tweet>"
    )


def deduplicate_documents(documents: list[Document]) -> list[Document]:
    """Remove repeated evidence while preserving the first retrieval order."""
    unique_by_key: dict[str, Document] = {}
    for document in documents:
        metadata = document.metadata or {}
        evidence_key = str(metadata.get("evidence_id") or "")
        if not evidence_key:
            evidence_key = " ".join(document.page_content.lower().split())
        unique_by_key.setdefault(evidence_key, document)
    return list(unique_by_key.values())


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
        for field_name, field_value in (("start_date", start_date), ("end_date", end_date)):
            if field_value and not date_pattern.match(field_value):
                return f"Error de validacion: {field_name} '{field_value}' no tiene el formato correcto YYYY-MM-DD."
            if field_value:
                try:
                    date.fromisoformat(field_value)
                except ValueError:
                    return f"Error de validacion: {field_name} '{field_value}' no es una fecha valida."

        clean_handles = [h.lstrip("@") for h in (user_handles or [])]

        try:
            filters = TweetFilters(
                start_date=start_date,
                end_date=end_date,
                user_handles=clean_handles,
                tickers=tickers or [],
                sentiment=sentiment,
                topics=topics or [],
            )
            qdrant_filter = filters.to_qdrant_filter()
        except ValueError as exc:
            return f"Error de validacion: {exc}"

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

        docs = deduplicate_documents(docs)
        if compressor:
            docs = list(compressor.compress_documents(docs, effective_query))
            for rank, doc in enumerate(docs, start=1):
                doc.metadata["rerank_rank"] = rank

        return "\n\n".join(format_tweet_doc(d) for d in docs)

    return search_tweets
