from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pyarrow.parquet as pq
from pipeline.src.enricher import TweetEnricher
from pipeline.src.processor import parse_s3_key, records_to_parquet_bytes


def test_parse_s3_key_valid():
    """Valida la extracción de metadatos de partición temporal desde la key de S3."""
    key = "data/year=2024/month=05/day=15/tweets_18-30-00.json"
    parsed = parse_s3_key(key)

    assert parsed["crawl_year"] == 2024
    assert parsed["crawl_month"] == 5
    assert parsed["crawl_day"] == 15
    assert parsed["crawl_timestamp"] is not None


def test_parse_s3_key_fallback():
    """Valida que una key con formato no estándar use fallback seguro de fecha actual."""
    key = "raw/other_format/tweets.json"
    parsed = parse_s3_key(key)

    assert "crawl_year" in parsed
    assert "crawl_month" in parsed
    assert "crawl_day" in parsed
    assert parsed["crawl_timestamp"] is not None


def test_records_to_parquet_bytes_schema():
    """Valida la conversión de registros enriquecidos a bytes Parquet válidos."""
    records = [
        {
            "tweet_id": "12345",
            "user_handle": "analista",
            "content": "GGAL presentó un gran balance trimestral.",
            "tweet_timestamp": "2026-05-15T18:30:00Z",
            "crawl_timestamp": "2026-05-15T19:00:00Z",
            "is_retweet": False,
            "has_image": False,
            "url": "https://x.com/analista/status/12345",
            "tickers": ["GGAL"],
            "sentiment": "bullish",
            "topics": ["acciones_locales", "balances"],
            "is_financial_insight": True,
            "crawl_year": 2026,
            "crawl_month": 5,
            "crawl_day": 15,
            "tweet_year": 2026,
            "tweet_month": 5,
            "tweet_day": 15,
        }
    ]

    parquet_bytes = records_to_parquet_bytes(records)
    assert isinstance(parquet_bytes, bytes)
    assert len(parquet_bytes) > 0

    # Leer el buffer en memoria con pyarrow para verificar integridad
    table = pq.read_table(BytesIO(parquet_bytes))
    assert table.num_rows == 1
    assert "tickers" in table.column_names
    assert "sentiment" in table.column_names
    assert table["sentiment"][0].as_py() == "bullish"


def test_enricher_fallback_on_exception():
    """Valida que TweetEnricher retorne objetos por defecto si OpenAI falla, sin lanzar excepción."""
    enricher = TweetEnricher(api_key="mock_key", model="mock-model")
    # Forzar error simulando excepción en OpenAI parse
    enricher.client = MagicMock()
    enricher.client.beta.chat.completions.parse.side_effect = RuntimeError("OpenAI rate limit")

    tweets = [
        {"tweet_id": "t1", "user_handle": "trader", "content": "compré más acciones hoy"},
        {"tweet_id": "t2", "user_handle": "inversor", "content": "el mercado está indeciso"},
    ]

    results = enricher.enrich_batch(tweets)

    assert len(results) == 2
    assert "t1" in results
    assert "t2" in results
    assert results["t1"].sentiment == "neutral"
    assert results["t1"].is_financial_insight is True
