from unittest.mock import MagicMock

from agent.src.vector_store import create_search_tweets_tool
from agent.src.workflows.crag import (
    AgentState,
    _maybe_summarize,
    _rewrite_query,
    build_agent_workflow,
)
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langchain_core.tools import tool


def test_agent_graph_compilation():
    """Valida que el grafo unificado compile con todos los nodos esperados."""
    graph = build_agent_workflow()

    assert graph is not None
    assert "maybe_summarize" in graph.nodes
    assert "agent_node" in graph.nodes
    assert "tools" in graph.nodes
    assert "synthesize" in graph.nodes


def test_create_search_tweets_tool_execution():
    """Valida que create_search_tweets_tool retorne una tool ejecutable que formatee tweets."""
    mock_client = MagicMock()
    mock_point = MagicMock()
    mock_point.payload = {
        "content": "Gran balance de $GGAL con ganancias record.",
        "metadata": {"user_handle": "bull_market", "tweet_timestamp": "2026-05-10"},
    }
    mock_response = MagicMock()
    mock_response.points = [mock_point]
    mock_client.query_points.return_value = mock_response

    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 128

    search_tool = create_search_tweets_tool(
        qdrant_client=mock_client,
        collection_name="tweets",
        embeddings=mock_embeddings,
    )

    assert search_tool.name == "search_tweets"

    result = search_tool.invoke({"query": "GGAL balance", "tickers": ["GGAL"]})
    assert "<<< TWEET >>>" in result
    assert "@bull_market" in result
    assert "ganancias record" in result


def test_query_rewriter_alias_expansion():
    """Valida que el optimizador de query expanda alias comunes como 'la gallega'."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "GGAL Grupo Financiero Galicia balance perspectivas"
    mock_llm.invoke.return_value = mock_response

    state: AgentState = {
        "query": "que dicen de la gallega hoy",
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
    mock_response.content = "bonos soberanos en dolares proyeccion 2024"
    mock_llm.invoke.return_value = mock_response

    state: AgentState = {
        "query": "vision de los bonos soberanos en 2024",
        "search_attempts": 0,
    }
    config = {"configurable": {"llm": mock_llm}}

    result = _rewrite_query(state, config)
    rewritten = result["rewritten_query"]

    assert "GD24" not in rewritten.upper()
    assert "AL24" not in rewritten.upper()


def test_agent_workflow_direct_conversation():
    """Valida que una charla casual responda directo sin ejecutar la herramienta."""

    @tool
    def dummy_tool(query: str) -> str:
        """Tool de prueba."""
        return "ok"

    agent_graph = build_agent_workflow(search_tool=dummy_tool)

    mock_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_response = AIMessage(content="Hola! En que puedo ayudarte hoy?")
    mock_bound_llm.invoke.return_value = mock_response
    mock_llm.bind_tools.return_value = mock_bound_llm

    config = {
        "configurable": {
            "llm": mock_llm,
            "search_tool": dummy_tool,
        }
    }

    initial_state = {
        "messages": [{"role": "user", "content": "Hola como estas?"}],
    }

    final_state = agent_graph.invoke(initial_state, config=config)

    assert len(final_state["messages"]) == 2
    assert final_state["messages"][-1].content == "Hola! En que puedo ayudarte hoy?"


def test_agent_workflow_tool_call_flow():
    """Valida el flujo con ToolNode: agent_node -> tools (ToolNode) -> synthesize -> END."""

    @tool
    def search_tweets(query: str, tickers: list[str] | None = None) -> str:
        """Busca tweets de prueba."""
        return "<<< TWEET >>>\nautor: @inversor\nfecha: 2026-05-10\ncontenido: Excelente trimestre para $GGAL con ganancias record.\n<<< /TWEET >>>"

    agent_graph = build_agent_workflow(search_tool=search_tweets)

    mock_llm = MagicMock()
    mock_bound_llm = MagicMock()

    mock_agent_resp = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_tweets",
                "args": {"query": "opiniones sobre Galicia $GGAL", "tickers": ["GGAL"]},
                "id": "call_123",
            }
        ],
    )

    mock_synth_resp = AIMessage(content="El mercado ve un solido balance de GGAL con ganancias record.")

    def llm_invoke_side_effect(messages, **kwargs):
        tags = kwargs.get("config", {}).get("tags", [])
        if "agent_synthesis" in tags:
            return mock_synth_resp
        return mock_agent_resp

    mock_llm.invoke.side_effect = llm_invoke_side_effect
    mock_bound_llm.invoke.return_value = mock_agent_resp
    mock_llm.bind_tools.return_value = mock_bound_llm

    config = {
        "configurable": {
            "llm": mock_llm,
            "search_tool": search_tweets,
        }
    }

    initial_state = {
        "messages": [{"role": "user", "content": "Que dicen de Galicia?"}],
    }

    final_state = agent_graph.invoke(initial_state, config=config)

    assert "response" in final_state
    assert "record" in final_state["response"]
    # Corroborar que en messages este la respuesta del agente, el ToolMessage y la sintesis
    msg_types = [m.type for m in final_state["messages"]]
    assert "tool" in msg_types


def test_maybe_summarize_noop_when_under_limit():
    """Valida que no se resuma si la conversacion esta por debajo del limite de tokens/mensajes."""
    mock_llm = MagicMock()
    state: AgentState = {
        "messages": [HumanMessage(content="Hola", id="msg_1")],
    }
    config = {
        "configurable": {
            "llm": mock_llm,
            "memory_token_limit": 4000,
            "memory_keep_messages": 10,
        }
    }
    result = _maybe_summarize(state, config)
    assert result == {}
    assert not mock_llm.invoke.called


def test_maybe_summarize_triggers_when_exceeding_limit():
    """Valida que _maybe_summarize genere un resumen y emita RemoveMessage para mensajes viejos."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = "El usuario pregunto sobre bonos soberanos y se le dio analisis."
    mock_llm.invoke.return_value = mock_resp

    messages = [
        HumanMessage(content=f"Mensaje largo numero {i} sobre el mercado local", id=f"msg_{i}") for i in range(15)
    ]
    state: AgentState = {"messages": messages}

    config = {
        "configurable": {
            "llm": mock_llm,
            "memory_token_limit": 10,  # Limite bajo para forzar resumen
            "memory_keep_messages": 3,
        }
    }

    result = _maybe_summarize(state, config)

    assert "summary" in result
    assert "bonos soberanos" in result["summary"]
    assert "messages" in result
    # Debe haber 12 RemoveMessage (15 - 3 = 12 viejos)
    removes = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
    assert len(removes) == 12
    assert removes[0].id == "msg_0"
    assert removes[-1].id == "msg_11"


def test_agent_app_configuration_merge_and_invoke():
    """Valida que AgentApp fusione la configuracion de servicios con thread_id y extra_configurable."""
    from agent.src.agent import AgentApp

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "response": "Respuesta"}

    services = {
        "llm": "mock_llm",
        "search_tool": "mock_tool",
        "memory_token_limit": 4000,
    }
    app = AgentApp(graph=mock_graph, services=services)

    config = app.get_config(thread_id="test_session", extra_configurable={"custom_param": 123})
    assert config["configurable"]["thread_id"] == "test_session"
    assert config["configurable"]["llm"] == "mock_llm"
    assert config["configurable"]["custom_param"] == 123

    res = app.invoke(messages=[{"role": "user", "content": "Hola"}], thread_id="test_session")
    assert res["response"] == "Respuesta"
    assert mock_graph.invoke.called


def test_lambda_handler_happy_path(monkeypatch):
    """Valida que lambda_handler procese el evento y retorne la respuesta esperada."""
    import json

    from agent.src.handler import lambda_handler

    mock_invoke = MagicMock(
        return_value={
            "messages": [AIMessage(content="Hola desde FinTwit!")],
            "response": "Hola desde FinTwit!",
        }
    )
    monkeypatch.setattr("agent.src.handler.agent_app.invoke", mock_invoke)

    event = {
        "body": json.dumps(
            {
                "messages": [{"role": "user", "content": "Hola"}],
                "thread_id": "thread_abc",
                "extra_configurable": {"foo": "bar"},
            }
        )
    }
    resp = lambda_handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["response"] == "Hola desde FinTwit!"
    mock_invoke.assert_called_once_with(
        messages=[{"role": "user", "content": "Hola"}],
        thread_id="thread_abc",
        extra_configurable={"foo": "bar"},
    )


def test_agentcore_entrypoint_invocation(monkeypatch):
    """Valida que agent_invocation procese el evento y llame a agent_app.invoke."""
    from agent.src import entrypoint

    mock_agent_app = MagicMock()
    mock_agent_app.invoke.return_value = {
        "messages": [AIMessage(content="Analisis de mercado local")],
        "response": "Analisis de mercado local",
    }
    monkeypatch.setattr(entrypoint, "agent_app", mock_agent_app)

    context = MagicMock()
    context.session_id = "session_xyz"
    res = entrypoint.agent_invocation({"prompt": "Que pasa con Galicia?"}, context)

    assert res["result"] == "Analisis de mercado local"
    assert res["response"] == "Analisis de mercado local"
    mock_agent_app.invoke.assert_called_once_with(
        messages=[{"role": "user", "content": "Que pasa con Galicia?"}],
        thread_id="session_xyz",
        extra_configurable=None,
    )


def test_agent_workflow_crag_correction_loop():
    """Valida el ciclo completo de auto-correccion de CRAG:
    agent_node -> tools (intento 1 irrelevante) -> check_relevance (score 2)
    -> rewrite_query -> tools (intento 2 relevante) -> check_relevance (score 9) -> synthesize -> END.
    """
    from agent.src.workflows.crag import RelevanceResult

    call_count = 0

    @tool
    def search_tweets(query: str, **kwargs) -> str:
        """Herramienta mock de busqueda de tweets."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "<<< TWEET >>>\nautor: @deportes\nfecha: 2024-05-10\ncontenido: River Plate le gano a Boca Juniors 2 a 0.\n<<< /TWEET >>>"
        return "<<< TWEET >>>\nautor: @inversor\nfecha: 2024-05-10\ncontenido: Excelente balance de $GGAL con ganancias solidas.\n<<< /TWEET >>>"

    agent_graph = build_agent_workflow(search_tool=search_tweets)

    mock_llm = MagicMock()
    mock_bound_llm = MagicMock()

    initial_agent_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_tweets",
                "args": {"query": "River Plate"},
                "id": "call_initial",
            }
        ],
    )
    mock_bound_llm.invoke.return_value = initial_agent_msg
    mock_llm.bind_tools.return_value = mock_bound_llm

    # Mock de with_structured_output para check_relevance
    mock_structured_llm = MagicMock()
    structured_call_count = 0

    def structured_invoke_side_effect(messages, **kwargs):
        nonlocal structured_call_count
        structured_call_count += 1
        if structured_call_count == 1:
            return RelevanceResult(score=2, relevant=False, reason="Tweets sobre futbol, no de finanzas.")
        return RelevanceResult(score=9, relevant=True, reason="Tweets financieros directamente sobre GGAL.")

    mock_structured_llm.invoke.side_effect = structured_invoke_side_effect
    mock_llm.with_structured_output.return_value = mock_structured_llm

    # Mock de llm.invoke para rewrite_query y synthesize
    mock_synth_msg = AIMessage(content="Analisis final: El mercado ve excelente balance de GGAL.")
    mock_rewrite_msg = AIMessage(content="GGAL Grupo Financiero Galicia balance")

    def llm_invoke_side_effect(messages, **kwargs):
        tags = kwargs.get("config", {}).get("tags", [])
        if "agent_synthesis" in tags:
            return mock_synth_msg
        if "crag_rewrite" in tags:
            return mock_rewrite_msg
        return initial_agent_msg

    mock_llm.invoke.side_effect = llm_invoke_side_effect

    config = {
        "configurable": {
            "llm": mock_llm,
            "search_tool": search_tweets,
            "relevance_threshold": 5.0,
            "max_attempts": 2,
        }
    }

    initial_state = {
        "messages": [{"role": "user", "content": "Que dicen de las acciones de Galicia?"}],
    }

    final_state = agent_graph.invoke(initial_state, config=config)

    assert call_count == 2, f"Se esperaban 2 llamadas a la tool pero hubo {call_count}"
    assert structured_call_count == 2, f"Se esperaban 2 evaluaciones pero hubo {structured_call_count}"
    assert final_state.get("relevance_score") == 9.0
    assert final_state.get("is_relevant") is True
    assert "excelente balance de GGAL" in final_state.get("response", "")

    tool_messages = [m for m in final_state["messages"] if getattr(m, "type", None) == "tool"]
    assert len(tool_messages) == 2
