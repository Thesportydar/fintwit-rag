from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from .config import PipelineConfig
from .embeddings import JinaEmbeddingService
from .enricher import TweetEnricher
from .models import TweetEnrichment

logger = logging.getLogger(__name__)

ARG_TZ = timezone(timedelta(hours=-3))
KEY_PATTERN = re.compile(r"data/year=(\d+)/month=(\d+)/day=(\d+)/tweets_(\d+)-(\d+)-(\d+)\.json$")
URL_PATTERN = re.compile(r"x\.com/([^/]+)/status/(\d+)")

ENRICHED_PARQUET_SCHEMA = pa.schema(
    [
        pa.field("tweet_id", pa.string()),
        pa.field("user_handle", pa.string()),
        pa.field("content", pa.string()),
        pa.field("tweet_timestamp", pa.timestamp("us", tz="UTC")),
        pa.field("crawl_timestamp", pa.timestamp("us", tz="UTC")),
        pa.field("is_retweet", pa.bool_()),
        pa.field("has_image", pa.bool_()),
        pa.field("url", pa.string()),
        pa.field("tickers", pa.list_(pa.string())),
        pa.field("sentiment", pa.string()),
        pa.field("topics", pa.list_(pa.string())),
        pa.field("is_financial_insight", pa.bool_()),
        pa.field("crawl_year", pa.int32()),
        pa.field("crawl_month", pa.int32()),
        pa.field("crawl_day", pa.int32()),
        pa.field("tweet_year", pa.int32()),
        pa.field("tweet_month", pa.int32()),
        pa.field("tweet_day", pa.int32()),
    ]
)


def parse_s3_key(key: str) -> dict | None:
    m = KEY_PATTERN.search(key)
    if not m:
        now = datetime.now(timezone.utc)
        return {
            "crawl_year": now.year,
            "crawl_month": now.month,
            "crawl_day": now.day,
            "crawl_timestamp": now,
        }
    year, month, day, hh, mm, ss = (int(x) for x in m.groups())
    local_dt = datetime(year, month, day, hh, mm, ss, tzinfo=ARG_TZ)
    utc_dt = local_dt.astimezone(timezone.utc)

    return {
        "crawl_year": year,
        "crawl_month": month,
        "crawl_day": day,
        "crawl_timestamp": utc_dt,
    }


def parse_tweet_record(raw: dict, crawl_meta: dict) -> dict:
    url = raw.get("url", "") or ""
    url_match = URL_PATTERN.search(url)
    user_handle = url_match.group(1) if url_match else (raw.get("user_handle") or "desconocido")
    tweet_id = url_match.group(2) if url_match else (str(raw.get("tweet_id")) if raw.get("tweet_id") else None)

    date_str = raw.get("date") or raw.get("tweet_timestamp") or ""
    tweet_ts = None
    if isinstance(date_str, datetime):
        tweet_ts = date_str if date_str.tzinfo else date_str.replace(tzinfo=timezone.utc)
    elif date_str:
        try:
            tweet_ts = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except Exception:
            tweet_ts = None

    return {
        "tweet_id": tweet_id,
        "user_handle": user_handle,
        "content": raw.get("content", "") or "",
        "tweet_timestamp": tweet_ts,
        "crawl_timestamp": crawl_meta["crawl_timestamp"],
        "is_retweet": bool(raw.get("is_retweet", False)),
        "has_image": bool(raw.get("has_image", False)),
        "url": url,
        "crawl_year": crawl_meta["crawl_year"],
        "crawl_month": crawl_meta["crawl_month"],
        "crawl_day": crawl_meta["crawl_day"],
        "tweet_year": tweet_ts.year if tweet_ts else None,
        "tweet_month": tweet_ts.month if tweet_ts else None,
        "tweet_day": tweet_ts.day if tweet_ts else None,
    }


def ensure_qdrant_collection(client: QdrantClient, collection_name: str, vector_size: int = 768):
    try:
        collections = client.get_collections().collections
        if not any(c.name == collection_name for c in collections):
            logger.info(f"Creando colección híbrida '{collection_name}' en Qdrant...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config={"dense": VectorParams(size=vector_size, distance=Distance.COSINE)},
                sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
    except Exception as exc:
        logger.warning(f"Aviso al verificar colección en Qdrant: {exc}")


def records_to_parquet_bytes(records: list[dict]) -> bytes:
    import pandas as pd

    df = pd.DataFrame(records)
    for col in ("tweet_timestamp", "crawl_timestamp"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)

    int_cols = ("crawl_year", "crawl_month", "crawl_day", "tweet_year", "tweet_month", "tweet_day")
    for col in int_cols:
        if col in df.columns:
            df[col] = df[col].astype("Int32")

    table = pa.Table.from_pandas(df, schema=ENRICHED_PARQUET_SCHEMA, preserve_index=False)
    buf = BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()


def process_tweet_records(
    raw_tweets: list[dict],
    crawl_meta: dict,
    enricher: TweetEnricher,
    embedder: JinaEmbeddingService,
    qdrant_client: QdrantClient,
    config: PipelineConfig,
    s3_client: Any = None,
    write_parquet: bool = True,
    dest_s3_key: str | None = None,
) -> dict:
    if not raw_tweets:
        return {"total_raw": 0, "processed": 0, "upserted_qdrant": 0}

    ensure_qdrant_collection(qdrant_client, config.collection_name)

    # 1. Limpieza y parseo de registros
    parsed_records = []
    for raw in raw_tweets:
        parsed = parse_tweet_record(raw, crawl_meta)
        if parsed.get("content"):
            parsed_records.append(parsed)

    total_records = len(parsed_records)
    logger.info(f"Procesando {total_records} tweets estructurados...")

    # 2. Enriquecimiento semántico en batches con LLM
    batch_size = config.enrichment_batch_size
    num_batches = math.ceil(total_records / batch_size)
    enriched_records = []

    for b in range(num_batches):
        batch = parsed_records[b * batch_size : (b + 1) * batch_size]
        enrichment_map = enricher.enrich_batch(batch)

        for rec in batch:
            t_id = str(rec["tweet_id"] or "")
            enr: TweetEnrichment = enrichment_map.get(
                t_id,
                TweetEnrichment(
                    tweet_id=t_id,
                    tickers=[],
                    sentiment="neutral",
                    topics=[],
                    is_financial_insight=True,
                ),
            )
            rec["tickers"] = enr.tickers
            rec["sentiment"] = enr.sentiment
            rec["topics"] = enr.topics
            rec["is_financial_insight"] = enr.is_financial_insight
            enriched_records.append(rec)

    # 3. Generación de Embeddings densos con Jina
    texts = [r["content"] for r in enriched_records]
    embeddings = embedder.embed_texts(texts, task="retrieval.passage")

    # 4. Preparación de Points y Upsert a Qdrant (Dense + Sparse BM25 server-side inference)
    points = []
    for idx, rec in enumerate(enriched_records):
        raw_id = rec.get("tweet_id")
        if raw_id and str(raw_id).isdigit():
            point_id = int(raw_id)
        else:
            point_id = idx + 1

        tweet_ts = rec["tweet_timestamp"].isoformat() if rec.get("tweet_timestamp") else None
        crawl_ts = rec["crawl_timestamp"].isoformat() if rec.get("crawl_timestamp") else None

        metadata = {
            "user_handle": rec["user_handle"],
            "tweet_timestamp": tweet_ts,
            "crawl_timestamp": crawl_ts,
            "is_retweet": rec["is_retweet"],
            "has_image": rec["has_image"],
            "url": rec["url"],
            "tickers": rec["tickers"],
            "sentiment": rec["sentiment"],
            "topics": rec["topics"],
            "is_financial_insight": rec["is_financial_insight"],
            "tweet_year": rec["tweet_year"],
            "tweet_month": rec["tweet_month"],
            "tweet_day": rec["tweet_day"],
            "crawl_year": rec["crawl_year"],
            "crawl_month": rec["crawl_month"],
            "crawl_day": rec["crawl_day"],
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        point = PointStruct(
            id=point_id,
            vector={
                "dense": embeddings[idx],
                "bm25": models.Document(
                    text=rec["content"],
                    model="Qdrant/bm25",
                ),
            },
            payload={
                "content": rec["content"],
                "metadata": metadata,
            },
        )
        points.append(point)

    if points:
        qdrant_client.upsert(collection_name=config.collection_name, points=points)
        logger.info(f"Upsert de {len(points)} puntos a Qdrant exitoso.")

    # 5. Escritura de Parquet enriquecido en S3
    parquet_written = False
    if write_parquet and s3_client and enriched_records:
        year = crawl_meta["crawl_year"]
        month = crawl_meta["crawl_month"]
        if not dest_s3_key:
            timestamp_str = datetime.now(timezone.utc).strftime("%H-%M-%S")
            dest_s3_key = (
                f"{config.s3_processed_prefix}/crawl_year={year}/crawl_month={month}/tweets_{timestamp_str}.parquet"
            )

        parquet_bytes = records_to_parquet_bytes(enriched_records)
        s3_client.put_object(
            Bucket=config.s3_processed_bucket,
            Key=dest_s3_key,
            Body=parquet_bytes,
            ContentType="application/octet-stream",
        )
        parquet_written = True
        logger.info(f"Parquet enriquecido guardado en s3://{config.s3_processed_bucket}/{dest_s3_key}")

    return {
        "total_raw": len(raw_tweets),
        "processed": len(enriched_records),
        "upserted_qdrant": len(points),
        "parquet_written": parquet_written,
    }
