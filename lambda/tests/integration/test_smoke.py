import os

import pytest

from src.config import AppConfig
from src.embeddings import JinaEmbeddingConfig, JinaEmbeddingProvider
from src.vector_store import QdrantStoreConfig, QdrantTweetVectorStore, TweetFilters


pytestmark = pytest.mark.integration


def test_app_config_loads_from_environment():
    config = AppConfig.from_env()

    assert config.jina_api_key
    assert config.qdrant_url
    assert config.collection_name


def test_jina_and_qdrant_live_search_roundtrip():
    config = AppConfig.from_env()
    jina = JinaEmbeddingProvider(
        JinaEmbeddingConfig(
            api_key=config.jina_api_key,
            embed_url=config.jina_embed_url,
            rerank_url=config.jina_rerank_url,
            embed_model=config.jina_embed_model,
            rerank_model=config.jina_rerank_model,
        )
    )
    store = QdrantTweetVectorStore(
        QdrantStoreConfig(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.collection_name,
        )
    )

    query_vector = jina.embed_query("bitcoin")
    results = store.query(query_vector=query_vector, limit=3, filters=TweetFilters.from_dict({}))

    assert isinstance(results.points, list)
    if results.points:
        point = results.points[0]
        assert "content" in point.payload
        assert "user_handle" in point.payload
        assert "tweet_timestamp" in point.payload


def test_qdrant_filter_translation_handles_empty_filters():
    assert TweetFilters.from_dict({}).to_qdrant_filter() is None
