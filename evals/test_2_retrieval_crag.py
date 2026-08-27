"""
Layer 2: Evaluación de Retrieval & Grafo CRAG
=============================================
Evalúa:
1. Calidad del Retrieval Híbrido mediante Contextual Relevancy (DeepEval / G-Eval).
2. Guardrails del Reescritor de Queries (expansión de alias y prevención de alucinación de tickers en fechas).
3. Mecanismo de auto-corrección del subgrafo CRAG ante evidencia de baja relevancia.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

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
from agent.src.config import AppConfig
from agent.src.llm import get_llm
from agent.src.workflows.crag import CRAGState, _rewrite_query, build_crag_workflow
from deepeval.test_case import LLMTestCase
from langchain_core.documents import Document

from evals.metrics import create_contextual_relevancy_metric


@pytest.fixture(scope="module")
def llm():
    config = AppConfig.from_env()
    return get_llm(provider=config.llm_provider)


def test_layer2_query_rewriter_guardrails(llm):
    """Evalúa que el reescritor expanda jerga financiera y respete fechas sin alucinar tickers."""
    print("\n--- [CAPA 2] Guardrails de Reescritura CRAG ---")

    # Caso 1: Expansión de jerga
    state1: CRAGState = {"query": "qué opinan de la gallega y los bonos soberanos", "search_attempts": 0}
    config = {"configurable": {"llm": llm}}
    res1 = _rewrite_query(state1, config)
    rewritten1 = res1["rewritten_query"].upper()
    print(f"Original: {state1['query']} -> Rewritten: {res1['rewritten_query']}")
    assert "GGAL" in rewritten1 or "GALICIA" in rewritten1, "Debe expandir 'la gallega' a GGAL"

    # Caso 2: Respeto estricto de años/fechas sin inventar tickers
    state2: CRAGState = {"query": "expectativas de la tasa del BCRA para 2024", "search_attempts": 0}
    res2 = _rewrite_query(state2, config)
    rewritten2 = res2["rewritten_query"].upper()
    print(f"Original: {state2['query']} -> Rewritten: {res2['rewritten_query']}")
    assert "GD24" not in rewritten2 and "AL24" not in rewritten2, "No debe inventar GD24 ni AL24 a partir de '2024'"


def test_layer2_contextual_relevancy_metric():
    """Evalúa la relevancia contextual de los fragmentos recuperados usando G-Eval."""
    print("\n--- [CAPA 2] Contextual Relevancy Metric (G-Eval) ---")

    query = "Cual es la situación de las reservas del BCRA y el tipo de cambio oficial?"
    relevant_context = [
        "El Banco Central (BCRA) compró hoy USD 120M en el MLC, acumulando reservas por USD 28.500M.",
        "El tipo de cambio oficial mayorista se ubicó en $910, con crawling peg al 2% mensual.",
        "Las reservas netas del BCRA mostraron una mejora acumulada de USD 1.200M en el último mes.",
    ]

    test_case = LLMTestCase(
        input=query,
        actual_output="Las reservas del BCRA crecieron a USD 28.500M tras compras por USD 120M, mientras el oficial se ubica en $910.",
        retrieval_context=relevant_context,
    )

    metric = create_contextual_relevancy_metric(threshold=0.7, model="gpt-4o-mini")
    metric.measure(test_case, _show_indicator=False)
    print(f"Score Contextual Relevancy: {metric.score:.2f} | Razón: {metric.reason}")
    assert metric.score >= 0.70


def test_layer2_crag_self_correction_trigger(llm):
    """Evalúa que si el contexto inicial es irrelevante, el flujo active el reintento."""
    print("\n--- [CAPA 2] Validación del Loop de Auto-Corrección CRAG ---")
    workflow = build_crag_workflow()

    # Mock de búsqueda que devuelve documentos sobre fútbol en vez de finanzas
    mock_vectorstore = MagicMock()
    mock_vectorstore.similarity_search.return_value = [
        Document(
            page_content="River Plate le ganó a Boca Juniors en el superclásico de fútbol 2 a 0 con goles de Borja.",
            metadata={"user_handle": "deportes_bot", "tweet_timestamp": "2024-05-10T12:00:00Z"},
        )
    ]

    class MockCompressor:
        def compress_documents(self, docs, query):
            return docs

    config = {
        "configurable": {
            "vectorstore": mock_vectorstore,
            "compressor": MockCompressor(),
            "llm": llm,
            "k": 5,
            "relevance_threshold": 5.0,
            "max_attempts": 2,
        }
    }

    input_state: CRAGState = {
        "query": "balance y proyecciones de YPFD",
        "search_attempts": 0,
        "documents": [],
    }

    result = workflow.invoke(input_state, config=config)
    print(f"Search attempts finales: {result.get('search_attempts')}")
    print(f"Relevance Score final: {result.get('relevance_score')}")

    # Debe haber ejecutado al menos 2 intentos de búsqueda tras rechazar el fútbol
    assert result.get("search_attempts", 1) >= 2
    assert result.get("relevance_score", 0) < 5.0
    print("[OK] Loop de auto-corrección disparado correctamente ante contexto espurio!")
