from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from qdrant_client import QdrantClient

from .config import PipelineConfig
from .embeddings import JinaEmbeddingService
from .enricher import TweetEnricher
from .processor import parse_s3_key, process_tweet_records

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context: Any = None) -> dict:
    logger.info(f"Evento EventBridge recibido: {json.dumps(event)}")

    detail = event.get("detail", {})
    bucket = detail.get("bucket")
    s3_key = detail.get("s3Key")

    if not bucket or not s3_key:
        logger.error("Faltan 'bucket' o 's3Key' en event.detail")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing bucket or s3Key in event detail"}),
        }

    config = PipelineConfig.from_env()

    s3_client = boto3.client("s3", region_name=config.aws_region)
    enricher = TweetEnricher(api_key=config.openai_api_key, model=config.enrichment_model)
    embedder = JinaEmbeddingService(
        api_key=config.jina_api_key,
        url=config.jina_embed_url,
        model=config.jina_embed_model,
    )
    qdrant_client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)

    try:
        # 1. Leer JSON de S3
        logger.info(f"Leyendo s3://{bucket}/{s3_key}...")
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        raw_data = json.loads(response["Body"].read().decode("utf-8"))

        if isinstance(raw_data, dict):
            raw_tweets = raw_data.get("tweets", [])
        elif isinstance(raw_data, list):
            raw_tweets = raw_data
        else:
            raw_tweets = []

        logger.info(f"Obtenidos {len(raw_tweets)} tweets crudos desde S3.")

        # 2. Metadata de crawl
        crawl_meta = parse_s3_key(s3_key)

        # 3. Derivar key de destino para Parquet
        # ej: data/year=2026/month=8/day=24/tweets_12-00-00.json -> processed/crawl_year=2026/crawl_month=8/tweets_12-00-00.parquet
        parquet_filename = os.path.basename(s3_key).replace(".json", ".parquet")
        dest_s3_key = f"{config.s3_processed_prefix}/crawl_year={crawl_meta['crawl_year']}/crawl_month={crawl_meta['crawl_month']}/{parquet_filename}"

        # 4. Procesamiento
        stats = process_tweet_records(
            raw_tweets=raw_tweets,
            crawl_meta=crawl_meta,
            enricher=enricher,
            embedder=embedder,
            qdrant_client=qdrant_client,
            config=config,
            s3_client=s3_client,
            write_parquet=True,
            dest_s3_key=dest_s3_key,
        )

        logger.info(f"Pipeline completado exitosamente: {stats}")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Batch processed successfully", "stats": stats}),
        }

    except Exception as exc:
        logger.error(f"Error procesando ingesta de tweets: {exc}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }
