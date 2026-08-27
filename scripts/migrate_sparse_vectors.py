#!/usr/bin/env python3
"""
Migración In-Place de Sparse Vectors (BM25) en Qdrant
=====================================================
Este script actualiza una colección existente de Qdrant (restaurada desde snapshot)
para agregar la configuración de sparse vectors y calcular el índice BM25 server-side
a partir del contenido ya almacenado en el payload de cada punto.

Costo de APIs externas: $0 (Qdrant calcula BM25 localmente en la EC2).

Uso:
    python migrate_sparse_vectors.py --dry-run
    python migrate_sparse_vectors.py --batch-size 500
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Cargar .env si existe
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from qdrant_client import QdrantClient, models
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sparse-migrator")


def migrate_sparse_vectors(
    qdrant_url: str,
    qdrant_api_key: str | None,
    collection_name: str = "tweets",
    batch_size: int = 500,
    dry_run: bool = False,
):
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    logger.info(f"Conectando a Qdrant en {qdrant_url} (colección: '{collection_name}')...")

    # 1. Verificar colección
    try:
        coll_info = client.get_collection(collection_name)
        logger.info(f"Colección encontrada. Total de puntos: {coll_info.points_count}")
    except Exception as e:
        logger.error(f"Error accediendo a la colección '{collection_name}': {e}")
        sys.exit(1)

    # 2. Agregar sparse vector 'bm25' si no existe
    has_sparse = coll_info.config.params.sparse_vectors and "bm25" in coll_info.config.params.sparse_vectors
    if not has_sparse:
        logger.info("Agregando nuevo vector sparse 'bm25' con IDF modifier vía create_vector_name...")
        if not dry_run:
            client.create_vector_name(
                collection_name=collection_name,
                vector_name="bm25",
                vector_name_config=models.SparseVectorNameConfig(
                    sparse=models.SparseVectorConfig(modifier=models.Modifier.IDF)
                ),
            )
            logger.info("[OK] Vector sparse 'bm25' creado exitosamente.")
    else:
        logger.info("La colección ya cuenta con el vector sparse 'bm25'.")

    # 3. Scroll y actualización de vectores BM25 en batches
    offset = None
    total_updated = 0
    pbar = tqdm(total=coll_info.points_count or 0, desc="Indexando BM25")

    while True:
        records, next_offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not records:
            break

        points_to_update = []
        for record in records:
            payload = record.payload or {}
            # El texto del tweet puede estar en 'content' o 'text'
            text = payload.get("content") or payload.get("text") or ""
            if not text:
                continue

            points_to_update.append(
                models.PointVectors(
                    id=record.id,
                    vector={"bm25": models.Document(text=text, model="Qdrant/bm25")},
                )
            )

        if points_to_update and not dry_run:
            client.update_vectors(
                collection_name=collection_name,
                points=points_to_update,
            )

        total_updated += len(points_to_update)
        pbar.update(len(records))

        if next_offset is None:
            break
        offset = next_offset

    pbar.close()
    logger.info(
        f"[DONE] Migración finalizada: {total_updated} puntos indexados con BM25 server-side (Dry Run: {dry_run})."
    )


def main():
    parser = argparse.ArgumentParser(description="Calcular sparse vectors BM25 in-place en Qdrant sin re-embeddear")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("COLLECTION_NAME", "tweets"))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    migrate_sparse_vectors(
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        collection_name=args.collection,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
