from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pyarrow.parquet as pq
import requests
from pipeline.src.enricher import (
    GeminiTweetEnricher,
    TweetEnricher,
)
from pipeline.src.processor import (
    TWEET_TIMESTAMP_FIELD,
    build_evidence_id,
    ensure_qdrant_collection,
    parse_s3_key,
    records_to_parquet_bytes,
)


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


def test_build_evidence_id_is_stable_for_platform_and_derived_records():
    assert build_evidence_id({"tweet_id": "123"}) == "tweet:123"

    record = {
        "url": "",
        "user_handle": "analista",
        "tweet_timestamp": "2026-05-15T18:30:00+00:00",
        "content": "GGAL presento un buen balance.",
    }
    first = build_evidence_id(record)
    second = build_evidence_id(dict(record))

    assert first == second
    assert first.startswith("derived:")
    assert len(first) == len("derived:") + 24


def test_ensure_qdrant_collection_creates_datetime_index_for_existing_collection():
    client = MagicMock()
    existing_collection = MagicMock()
    existing_collection.name = "tweets"
    client.get_collections.return_value.collections = [existing_collection]
    client.get_collection.return_value.payload_schema = {}

    ensure_qdrant_collection(client, "tweets")

    client.create_collection.assert_not_called()
    client.create_payload_index.assert_called_once_with(
        collection_name="tweets",
        field_name=TWEET_TIMESTAMP_FIELD,
        field_schema="datetime",
        wait=True,
    )


def test_ensure_qdrant_collection_does_not_recreate_datetime_index():
    client = MagicMock()
    existing_collection = MagicMock()
    existing_collection.name = "tweets"
    client.get_collections.return_value.collections = [existing_collection]
    timestamp_index = MagicMock()
    timestamp_index.data_type.value = "datetime"
    client.get_collection.return_value.payload_schema = {TWEET_TIMESTAMP_FIELD: timestamp_index}

    ensure_qdrant_collection(client, "tweets")

    client.create_payload_index.assert_not_called()


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
    assert results["t1"].sentiment == "unknown"
    assert results["t1"].is_financial_insight is None
    assert results["t1"].enrichment_status == "unclassified"
    assert results["t1"].confidence is None
    assert results["t1"].tickers == []


def test_enricher_fallback_does_not_infer_tickers_without_model():
    enricher = TweetEnricher(api_key="mock_key", model="mock-model")
    enricher.client = MagicMock()
    enricher.client.beta.chat.completions.parse.side_effect = RuntimeError("provider unavailable")

    results = enricher.enrich_batch([{"tweet_id": "t1", "content": "La gallega y el $AL30 siguen firmes"}])

    assert results["t1"].enrichment_status == "unclassified"
    assert results["t1"].tickers == []


def test_gemini_enricher_parses_structured_response(monkeypatch):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"items":[{"tweet_id":"t1","tickers":["GGAL"],"sentiment":"bullish","topics":["acciones_locales"],"is_financial_insight":true,"enrichment_status":"classified","enrichment_version":"v1","confidence":0.9}]}'
                        }
                    ]
                }
            }
        ]
    }
    monkeypatch.setattr("pipeline.src.enricher.requests.post", lambda *args, **kwargs: response)

    enricher = GeminiTweetEnricher(api_key="key-1", model="gemini-test")
    results = enricher.enrich_batch([{"tweet_id": "t1", "user_handle": "trader", "content": "La gallega sube"}])

    assert results["t1"].sentiment == "bullish"
    assert results["t1"].tickers == ["GGAL"]
    assert results["t1"].enrichment_status == "classified"


def test_gemini_enricher_normalizes_model_metadata(monkeypatch):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"items":[{"tweet_id":"t1","tickers":["$GGAL","not a ticker"],'
                                '"sentiment":"unknown","topics":["acciones_locales","inventado"],'
                                '"is_financial_insight":null,"enrichment_status":"unclassified",'
                                '"enrichment_version":"old","confidence":null}]}'
                            )
                        }
                    ]
                }
            }
        ]
    }
    monkeypatch.setattr("pipeline.src.enricher.requests.post", lambda *args, **kwargs: response)

    enricher = GeminiTweetEnricher(api_key="key-1", model="gemini-test")
    results = enricher.enrich_batch([{"tweet_id": "t1", "content": "La gallega sigue firme"}])

    assert results["t1"].tickers == ["GGAL"]
    assert results["t1"].topics == ["acciones_locales"]
    assert results["t1"].enrichment_status == "unclassified"
    assert results["t1"].enrichment_version == "v1"


def test_gemini_enricher_falls_back_to_unclassified_on_request_error(monkeypatch):
    response = MagicMock()
    response.raise_for_status.side_effect = requests.RequestException("temporarily unavailable")
    monkeypatch.setattr("pipeline.src.enricher.requests.post", lambda *args, **kwargs: response)

    enricher = GeminiTweetEnricher(api_key="key-1", model="gemini-test")
    results = enricher.enrich_batch([{"tweet_id": "t1", "content": "mercado neutral"}])

    assert results["t1"].enrichment_status == "unclassified"
    assert results["t1"].tickers == []
