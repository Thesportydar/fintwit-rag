from __future__ import annotations

from unittest.mock import MagicMock

from agent.src.vector_store import (
    TweetFilters,
    hybrid_search_tweets,
)


def test_tweet_filters_date_range():
    """Valida la generación de filtro Qdrant para rango de fechas por año."""
    filters = TweetFilters(start_date="2025-01-01", end_date="2026-12-31")
    q_filter = filters.to_qdrant_filter()
    assert q_filter is not None
    assert len(q_filter.must) == 1
    assert q_filter.must[0].key == "metadata.tweet_year"
    assert q_filter.must[0].range.gte == 2025
    assert q_filter.must[0].range.lte == 2026


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
