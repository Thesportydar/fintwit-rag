#!/usr/bin/env python3
"""
Backfill masivo de Tweets con Enriquecimiento Semántico y Vector Store
======================================================================
Descarga JSONs históricos de S3, ejecuta el enriquecimiento semántico con LLM
(tickers, sentimiento, tópicos), genera embeddings con Jina, realiza el upsert
en Qdrant y guarda los archivos Parquet Snappy particionados en S3.

Uso:
    python backfill_tweets.py --dry-run
    python backfill_tweets.py --limit 5
    python backfill_tweets.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from qdrant_client import QdrantClient
from tqdm import tqdm

# Cargar .env si existe
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Añadir lambdas/pipeline/src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambdas" / "pipeline"))

from src.config import PipelineConfig
from src.embeddings import JinaEmbeddingService
from src.enricher import TweetEnricher
from src.processor import parse_s3_key, process_tweet_records


def list_s3_json_keys(s3_client, bucket: str, prefix: str = "data/") -> list[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if k.endswith(".json"):
                keys.append(k)
    return keys


def run_backfill(
    source_bucket: str = "inaqui-prod-twitter-scraper",
    source_prefix: str = "data/",
    limit: int | None = None,
    dry_run: bool = False,
    aws_profile: str | None = None,
):
    print("=" * 70)
    print("[RUN] FINTWIT BACKFILL PIPELINE: ENRIQUECIMIENTO & VECTOR STORE")
    print("=" * 70)

    config = PipelineConfig.from_env()

    session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
    s3_client = session.client("s3")

    print(f"[S3] Buscando archivos JSON en s3://{source_bucket}/{source_prefix}...")
    keys = list_s3_json_keys(s3_client, source_bucket, source_prefix)
    print(f"[FILES] Encontrados {len(keys)} archivos JSON.")

    if limit:
        keys = keys[:limit]
        print(f"[WARN] Limitado a los primeros {limit} archivos.")

    if not keys:
        print("No hay archivos para procesar.")
        return

    if dry_run:
        print("\n[DRY-RUN] MODO DRY RUN: No se realizarán llamadas al LLM ni escrituras.")
        for k in keys[:5]:
            print(f"  - Planificado: {k}")
        if len(keys) > 5:
            print(f"  ... y {len(keys) - 5} archivos más.")
        return

    enricher = TweetEnricher(api_key=config.openai_api_key, model=config.enrichment_model)
    embedder = JinaEmbeddingService(
        api_key=config.jina_api_key,
        url=config.jina_embed_url,
        model=config.jina_embed_model,
    )
    qdrant_client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)

    total_stats = {"files": 0, "raw_tweets": 0, "processed_tweets": 0, "upserted_qdrant": 0}

    for key in tqdm(keys, desc="Procesando archivos JSON"):
        try:
            obj = s3_client.get_object(Bucket=source_bucket, Key=key)
            raw_content = json.loads(obj["Body"].read().decode("utf-8"))

            if isinstance(raw_content, dict):
                raw_tweets = raw_content.get("tweets", [])
            elif isinstance(raw_content, list):
                raw_tweets = raw_content
            else:
                raw_tweets = []

            if not raw_tweets:
                continue

            crawl_meta = parse_s3_key(key)
            parquet_filename = os.path.basename(key).replace(".json", ".parquet")
            dest_key = f"{config.s3_processed_prefix}/crawl_year={crawl_meta['crawl_year']}/crawl_month={crawl_meta['crawl_month']}/{parquet_filename}"

            stats = process_tweet_records(
                raw_tweets=raw_tweets,
                crawl_meta=crawl_meta,
                enricher=enricher,
                embedder=embedder,
                qdrant_client=qdrant_client,
                config=config,
                s3_client=s3_client,
                write_parquet=True,
                dest_s3_key=dest_key,
            )

            total_stats["files"] += 1
            total_stats["raw_tweets"] += stats["total_raw"]
            total_stats["processed_tweets"] += stats["processed"]
            total_stats["upserted_qdrant"] += stats["upserted_qdrant"]

        except Exception as exc:
            print(f"[WARN] Error procesando {key}: {exc}")

    print("\n" + "=" * 70)
    print("[OK] BACKFILL COMPLETADO")
    print(f"  - Archivos procesados: {total_stats['files']}")
    print(f"  - Tweets crudos leídos: {total_stats['raw_tweets']}")
    print(f"  - Tweets enriquecidos: {total_stats['processed_tweets']}")
    print(f"  - Puntos subidos a Qdrant: {total_stats['upserted_qdrant']}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Backfill y enriquecimiento semántico de tweets a Qdrant y Parquet")
    parser.add_argument("--source-bucket", default="inaqui-prod-twitter-scraper", help="Bucket S3 origen")
    parser.add_argument("--source-prefix", default="data/", help="Prefijo S3 origen")
    parser.add_argument("--limit", type=int, default=None, help="Límite de archivos JSON a procesar")
    parser.add_argument("--dry-run", action="store_true", help="Simular ejecución sin realizar cambios")
    parser.add_argument("--profile", default=None, help="Perfil de AWS CLI")

    args = parser.parse_args()

    run_backfill(
        source_bucket=args.source_bucket,
        source_prefix=args.source_prefix,
        limit=args.limit,
        dry_run=args.dry_run,
        aws_profile=args.profile,
    )


if __name__ == "__main__":
    main()
