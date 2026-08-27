"""
Layer 3: Evaluación de Generación & Agente FinTwit
==================================================
Evalúa end-to-end la calidad de las respuestas generadas:
1. Faithfulness (Groundedness / Cero alucinaciones contra el contexto).
2. FinTwit Answer Relevancy (Pertinencia y concisión de la respuesta financiera).
3. FinTwit Market Synthesis (Métrica custom G-Eval para balance de consensos financieros).
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
from deepeval.test_case import LLMTestCase

from evals.metrics import (
    create_faithfulness_metric,
    create_fintwit_answer_relevancy_metric,
    create_fintwit_synthesis_metric,
)

GOLDEN_DATASET_PATH = Path(__file__).parent / "data" / "golden_eval_dataset.json"


@pytest.fixture(scope="module")
def golden_test_cases():
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_layer3_faithfulness_and_relevancy(golden_test_cases):
    """Evalúa que las respuestas sintéticas no contengan alucinaciones y sean relevantes."""
    print("\n--- [CAPA 3] Faithfulness & Answer Relevancy Evaluation (G-Eval) ---")

    faithfulness_metric = create_faithfulness_metric(threshold=0.8, model="gpt-4o-mini")
    relevancy_metric = create_fintwit_answer_relevancy_metric(threshold=0.7, model="gpt-4o-mini")

    for case in golden_test_cases[:3]:
        query = case["query"]
        context = case["retrieval_context"]
        actual_output = case["expected_output"]

        test_case = LLMTestCase(
            input=query,
            actual_output=actual_output,
            retrieval_context=context,
        )

        faithfulness_metric.measure(test_case, _show_indicator=False)
        relevancy_metric.measure(test_case, _show_indicator=False)

        print(f"\nConsulta: '{query}'")
        print(f"  - Faithfulness Score: {faithfulness_metric.score:.2f} (Pasa: {faithfulness_metric.is_successful()})")
        print(f"  - Relevancy Score: {relevancy_metric.score:.2f} (Pasa: {relevancy_metric.is_successful()})")

        assert faithfulness_metric.score >= 0.80, f"Faithfulness falló en '{query}': {faithfulness_metric.reason}"
        assert relevancy_metric.score >= 0.70, f"Relevancy falló en '{query}': {relevancy_metric.reason}"


def test_layer3_fintwit_synthesis_custom_geval(golden_test_cases):
    """Evalúa la calidad de síntesis financiera y consenso con la métrica custom G-Eval."""
    print("\n--- [CAPA 3] FinTwit Market Synthesis (G-Eval) ---")

    synthesis_metric = create_fintwit_synthesis_metric(model="gpt-4o-mini", threshold=0.7)

    # Caso con opiniones mixtas (Galicia con récord + advertencia por mora)
    galicia_case = next((c for c in golden_test_cases if "galicia" in c["query"].lower()), golden_test_cases[0])

    test_case = LLMTestCase(
        input=galicia_case["query"],
        actual_output=galicia_case["expected_output"],
        retrieval_context=galicia_case["retrieval_context"],
    )

    synthesis_metric.measure(test_case, _show_indicator=False)
    print(f"\nConsulta: '{galicia_case['query']}'")
    print(f"  - G-Eval Synthesis Score: {synthesis_metric.score:.2f}")
    print(f"  - Razón: {synthesis_metric.reason}")

    assert synthesis_metric.score >= 0.70, f"G-Eval Synthesis falló: {synthesis_metric.reason}"
