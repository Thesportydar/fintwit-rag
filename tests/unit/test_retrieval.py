from __future__ import annotations

from unittest.mock import MagicMock

from agent.src.vector_store import (
    TweetFilters,
    deduplicate_documents,
    hybrid_search_tweets,
)
from langchain_core.documents import Document


def test_tweet_filters_date_range():
    """Valida que el rango use limites exactos de calendario."""
    filters = TweetFilters(start_date="2025-01-01", end_date="2026-12-31")
    q_filter = filters.to_qdrant_filter()
    assert q_filter is not None
    assert len(q_filter.must) == 1
    condition = q_filter.must[0].must[0]
    assert condition.key == "metadata.tweet_timestamp"
    assert condition.range.gte.isoformat() == "2025-01-01T00:00:00+00:00"
    assert condition.range.lt.isoformat() == "2027-01-01T00:00:00+00:00"


def test_tweet_filters_partial_dates_use_day_precision():
    """Valida que un rango parcial no incluya tweets fuera de sus dias."""
    filters = TweetFilters(start_date="2025-03-15", end_date="2025-03-17")
    q_filter = filters.to_qdrant_filter()
    condition = q_filter.must[0].must[0]

    assert condition.range.gte.isoformat() == "2025-03-15T00:00:00+00:00"
    assert condition.range.lt.isoformat() == "2025-03-18T00:00:00+00:00"


def test_tweet_filters_metadata_facets():
    """Valida filtros de activos, sentimiento y topicos enriquecidos."""
    filters = TweetFilters(
        tickers=["GGAL"],
        sentiment="bullish",
        topics=["acciones_locales"],
    )
    q_filter = filters.to_qdrant_filter()

    assert q_filter is not None
    assert q_filter.must[0].key == "metadata.tickers"
    assert q_filter.must[0].match.any == ["GGAL"]
    assert q_filter.must[1].key == "metadata.topics"
    assert q_filter.must[2].key == "metadata.sentiment"


def test_tweet_filters_reject_reversed_dates():
    """Valida que un rango invertido no se convierta en una busqueda silenciosa."""
    filters = TweetFilters(start_date="2025-04-01", end_date="2025-03-31")

    try:
        filters.to_qdrant_filter()
    except ValueError as exc:
        assert "posterior" in str(exc)
    else:
        raise AssertionError("Se esperaba un error para un rango invertido")


def test_tweet_filters_clean_handles():
    """Valida que los handles se limpien removiendo el prefijo @."""
    filters = TweetFilters(user_handles=["@vivalabolsa", "@InversorPerga"])
    q_filter = filters.to_qdrant_filter()
    assert q_filter is not None
    assert len(q_filter.must) == 1
    assert q_filter.must[0].key == "metadata.user_handle"
    assert q_filter.must[0].match.any == ["@vivalabolsa", "@InversorPerga"]


def test_tweet_filters_empty_returns_none():
    """Valida que un objeto TweetFilters vacío no cree condiciones innecesarias."""
    filters = TweetFilters()
    assert filters.to_qdrant_filter() is None


def test_hybrid_search_query_construction():
    """Valida que hybrid_search_tweets arme los prefetches densos y sparse BM25 con fusión RRF."""
    mock_client = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 768

    class MockPoint:
        def __init__(self, id, content, metadata):
            self.id = id
            self.payload = {"content": content, "metadata": metadata}

    class MockResponse:
        points = [
            MockPoint(
                id=1,
                content="Excelente jornada para $GGAL y los bancos locales.",
                metadata={"user_handle": "bull_market", "tweet_timestamp": "2026-05-10T15:00:00Z"},
            )
        ]

    mock_client.query_points.return_value = MockResponse()

    filters = TweetFilters(start_date="2026-01-01", end_date="2026-12-31")
    q_filter = filters.to_qdrant_filter()

    docs = hybrid_search_tweets(
        client=mock_client,
        collection_name="tweets",
        query="opiniones sobre el balance de Galicia",
        embeddings=mock_embeddings,
        qdrant_filter=q_filter,
        limit=20,
    )

    assert len(docs) == 1
    assert docs[0].page_content == "Excelente jornada para $GGAL y los bancos locales."
    assert docs[0].metadata["user_handle"] == "bull_market"
    assert docs[0].metadata["evidence_id"] == "qdrant:1"
    assert docs[0].metadata["retrieval_channel"] == "hybrid_rrf"
    assert docs[0].metadata["retrieval_rank"] == 1

    # Verificar argumentos enviados a Qdrant query_points
    assert mock_client.query_points.called
    kwargs = mock_client.query_points.call_args[1]
    assert kwargs["collection_name"] == "tweets"
    assert len(kwargs["prefetch"]) == 2

    # Prefetch 1: Vector Denso (sin nombre usando el default)
    dense_prefetch = kwargs["prefetch"][0]
    assert dense_prefetch.using is None
    assert dense_prefetch.query == [0.1] * 768

    # Prefetch 2: Vector Sparse BM25 server-side
    sparse_prefetch = kwargs["prefetch"][1]
    assert sparse_prefetch.using == "bm25"
    assert sparse_prefetch.query.model == "Qdrant/bm25"


def test_deduplicate_documents_preserves_first_evidence_order():
    documents = [
        Document(page_content="GGAL sube", metadata={"evidence_id": "tweet:1"}),
        Document(page_content="GGAL sube duplicado", metadata={"evidence_id": "tweet:1"}),
        Document(page_content="AL30 firme", metadata={"evidence_id": "tweet:2"}),
    ]

    unique = deduplicate_documents(documents)

    assert [doc.metadata["evidence_id"] for doc in unique] == ["tweet:1", "tweet:2"]
