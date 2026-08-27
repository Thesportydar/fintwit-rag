"""
Layer 1: Evaluación de Ingesta & Enriquecimiento Semántico
==========================================================
Evalúa la precisión del componente `TweetEnricher` en:
1. Extracción y normalización de tickers con jerga de FinTwit.
2. Clasificación de polaridad de sentimiento (bullish, bearish, neutral).
3. Filtrado de ruido / memes / saludos (is_financial_insight == False).
"""

from __future__ import annotations

import json
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

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

LAMBDAS_ROOT = Path(__file__).parent.parent / "lambdas"
if str(LAMBDAS_ROOT) not in sys.path:
    sys.path.insert(0, str(LAMBDAS_ROOT))

import pytest
from pipeline.src.config import PipelineConfig
from pipeline.src.enricher import TweetEnricher

BENCHMARK_PATH = Path(__file__).parent / "data" / "benchmark_ingestion.json"


@pytest.fixture(scope="module")
def benchmark_data():
    with open(BENCHMARK_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def enricher():
    config = PipelineConfig.from_env()
    return TweetEnricher(api_key=config.openai_api_key, model=config.enrichment_model)


def test_layer1_ticker_extraction_precision(benchmark_data, enricher):
    """Evalúa que los tickers extraídos coincidan con los esperados en el benchmark."""
    print("\n--- [CAPA 1] Evaluación de Extracción de Tickers ---")
    results = enricher.enrich_batch(benchmark_data)

    total = 0
    correct = 0

    for item in benchmark_data:
        t_id = item["tweet_id"]
        expected_tickers = {t.upper() for t in item["expected_tickers"]}
        actual = results.get(t_id)

        assert actual is not None, f"Falta resultado para {t_id}"
        actual_tickers = {t.upper() for t in actual.tickers}

        # Si ambos son vacíos o hay coincidencia
        if expected_tickers == actual_tickers:
            correct += 1
        elif expected_tickers.issubset(actual_tickers) or actual_tickers.issubset(expected_tickers):
            # Acierto parcial
            correct += 0.8

        total += 1
        print(f"[{t_id}] Esperados: {list(expected_tickers)} | Obtenidos: {list(actual_tickers)}")

    accuracy = correct / total
    print(f"Precisión de extracción de Tickers: {accuracy * 100:.1f}%")
    assert accuracy >= 0.75, f"La precisión de tickers ({accuracy:.2f}) es menor al threshold de 0.75"


def test_layer1_noise_filter_precision(benchmark_data, enricher):
    """Evalúa que el filtro de ruido (is_financial_insight) distinga memes/saludos de información real."""
    print("\n--- [CAPA 1] Evaluación de Filtro de Ruido (is_financial_insight) ---")
    results = enricher.enrich_batch(benchmark_data)

    correct = 0
    total = len(benchmark_data)

    for item in benchmark_data:
        t_id = item["tweet_id"]
        expected_insight = item["expected_insight"]
        actual = results.get(t_id)

        assert actual is not None
        if actual.is_financial_insight == expected_insight:
            correct += 1
        else:
            print(f"[WARN] Discrepancia en {t_id}: esperado={expected_insight}, obtenido={actual.is_financial_insight}")

    accuracy = correct / total
    print(f"Precisión del filtro de ruido: {accuracy * 100:.1f}%")
    assert accuracy >= 0.85, f"La precisión de detección de ruido ({accuracy:.2f}) es menor al threshold de 0.85"


def test_layer1_sentiment_alignment(benchmark_data, enricher):
    """Evalúa la coherencia de la polaridad de sentimiento asignada."""
    print("\n--- [CAPA 1] Evaluación de Clasificación de Sentimiento ---")
    results = enricher.enrich_batch(benchmark_data)

    financial_items = [i for i in benchmark_data if i["expected_insight"]]
    correct = 0

    for item in financial_items:
        t_id = item["tweet_id"]
        expected_sentiment = item["expected_sentiment"]
        actual = results.get(t_id)

        if actual.sentiment == expected_sentiment:
            correct += 1
        elif actual.sentiment in ("bullish", "neutral") and expected_sentiment in ("bullish", "neutral"):
            correct += 0.5

    accuracy = correct / len(financial_items)
    print(f"Alineación de sentimiento en tweets financieros: {accuracy * 100:.1f}%")
    assert accuracy >= 0.70, f"La precisión de sentimiento ({accuracy:.2f}) es menor al threshold de 0.70"
