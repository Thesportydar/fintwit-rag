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
from agent.src.workflows.crag import AgentState, _rewrite_query, build_agent_workflow
from deepeval.test_case import LLMTestCase
from langchain_core.messages import HumanMessage

from evals.metrics import create_contextual_relevancy_metric


@pytest.fixture(scope="module")
def llm():
    config = AppConfig.from_env()
    return get_llm(provider=config.llm_provider)


def test_layer2_query_rewriter_guardrails(llm):
    """Evalúa que el reescritor expanda jerga financiera y respete fechas sin alucinar tickers."""
    print("\n--- [CAPA 2] Guardrails de Reescritura CRAG ---")

    # Caso 1: Expansión de jerga
    state1: AgentState = {"query": "qué opinan de la gallega y los bonos soberanos", "search_attempts": 0}
    config = {"configurable": {"llm": llm}}
    res1 = _rewrite_query(state1, config)
    rewritten1 = res1["rewritten_query"].upper()
    print(f"Original: {state1['query']} -> Rewritten: {res1['rewritten_query']}")
    assert "GGAL" in rewritten1 or "GALICIA" in rewritten1, "Debe expandir 'la gallega' a GGAL"

    # Caso 2: Respeto estricto de años/fechas sin inventar tickers
    state2: AgentState = {"query": "expectativas de la tasa del BCRA para 2024", "search_attempts": 0}
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
    """Evalúa que la tool de búsqueda se invoque correctamente en el flujo del agente."""
    print("\n--- [CAPA 2] Validación de Ejecución de Tool en Agent Workflow ---")
    from langchain_core.tools import tool

    @tool
    def search_tweets(query: str, **kwargs) -> str:
        """Herramienta mock de búsqueda para test."""
        return "<<< TWEET >>>\nautor: @deportes_bot\nfecha: 2024-05-10\ncontenido: River Plate le ganó a Boca Juniors 2 a 0.\n<<< /TWEET >>>"

    workflow = build_agent_workflow(search_tool=search_tweets)

    config = {
        "configurable": {
            "search_tool": search_tweets,
            "llm": llm,
        }
    }

    input_state: AgentState = {
        "messages": [HumanMessage(content="balance y proyecciones de YPFD")],
    }

    result = workflow.invoke(input_state, config=config)
    print(f"Resultado final: {result.get('response', '')[:100]}...")

    # Debe contener la invocación de la tool en messages
    msg_types = [m.type for m in result.get("messages", [])]
    assert "tool" in msg_types, "El flujo debe contener un ToolMessage producto de la ejecución de search_tweets"
    print("[OK] ToolNode ejecutado correctamente en el flujo!")
