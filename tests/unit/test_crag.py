from unittest.mock import MagicMock

from agent.src.workflows.crag import (
    CRAGState,
    _rewrite_query,
    build_crag_workflow,
)
from langchain_core.documents import Document


def test_crag_graph_compilation():
    """Valida que el grafo StateGraph de CRAG compile sin errores de tipos o aristas."""
    graph = build_crag_workflow()
    assert graph is not None
    # Verificar nodos clave
    assert "rewrite_query" in graph.nodes
    assert "search_and_rerank" in graph.nodes
    assert "check_relevance" in graph.nodes
    assert "format_evidence" in graph.nodes


def test_query_rewriter_alias_expansion():
    """Valida que el optimizador de query expanda alias comunes como 'la gallega'."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "GGAL Grupo Financiero Galicia balance perspectivas"
    mock_llm.invoke.return_value = mock_response

    state: CRAGState = {
        "query": "qué dicen de la gallega hoy",
        "search_attempts": 0,
    }
    config = {"configurable": {"llm": mock_llm}}

    result = _rewrite_query(state, config)
    rewritten = result["rewritten_query"]

    assert "GGAL" in rewritten.upper() or "GALICIA" in rewritten.upper()
    assert result["search_attempts"] == 1


def test_query_rewriter_date_no_ticker_hallucination():
    """Valida que el optimizador no convierta años en tickers inexistentes (ej: 2024 -> GD24)."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "bonos soberanos en dólares proyección 2024"
    mock_llm.invoke.return_value = mock_response

    state: CRAGState = {
        "query": "visión de los bonos soberanos en 2024",
        "search_attempts": 0,
    }
    config = {"configurable": {"llm": mock_llm}}

    result = _rewrite_query(state, config)
    rewritten = result["rewritten_query"]

    assert "GD24" not in rewritten.upper()
    assert "AL24" not in rewritten.upper()


def test_crag_workflow_execution_with_mock_search():
    """Valida la ejecución de punta a punta del grafo CRAG usando un buscador mockeado."""
    graph = build_crag_workflow()

    def mock_search(query: str, filter=None, k: int = 50):
        return [
            Document(
                page_content="Gran balance de $GGAL con ganancias récord.",
                metadata={"user_handle": "bull_market", "tweet_timestamp": "2026-05-10"},
            )
        ]

    mock_llm = MagicMock()
    mock_compressor = MagicMock()
    mock_compressor.compress_documents.side_effect = lambda docs, q: docs

    mock_relevance_result = MagicMock()
    mock_relevance_result.score = 9
    mock_relevance_result.relevant = True
    mock_relevance_result.reason = "Altamente relevante para GGAL"

    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = mock_relevance_result
    mock_llm.with_structured_output.return_value = mock_structured_llm

    mock_rewriter_resp = MagicMock()
    mock_rewriter_resp.content = "GGAL balance ganancias récord"
    mock_llm.invoke.return_value = mock_rewriter_resp

    config = {
        "configurable": {
            "search_fn": mock_search,
            "llm": mock_llm,
            "compressor": mock_compressor,
            "relevance_threshold": 5.0,
            "max_attempts": 2,
        }
    }

    initial_state = {
        "query": "qué dicen del balance de galicia",
        "search_attempts": 0,
        "documents": [],
    }

    final_state = graph.invoke(initial_state, config=config)

    assert len(final_state.get("documents", [])) > 0
    assert final_state["documents"][0].metadata["user_handle"] == "bull_market"
    assert final_state["relevance_score"] >= 5.0
