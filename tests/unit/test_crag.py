from unittest.mock import MagicMock

from agent.src.vector_store import create_search_tweets_tool
from agent.src.workflows.crag import (
    AgentState,
    _agent_node,
    _check_relevance,
    _has_temporal_coverage,
    _maybe_summarize,
    _rewrite_query,
    _synthesis_context_messages,
    build_agent_workflow,
)
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langchain_core.tools import tool


def test_agent_graph_compilation():
    """Valida que el grafo unificado compile con todos los nodos esperados."""
    graph = build_agent_workflow()

    assert graph is not None
    assert "maybe_summarize" in graph.nodes
    assert "agent_node" in graph.nodes
    assert {"agent_node", "tools", "assess_coverage", "synthesize"} <= set(graph.nodes)
    assert "tools" in graph.nodes
    assert "assess_coverage" in graph.nodes
    assert "synthesize" in graph.nodes


def test_temporal_coverage_accepts_open_ended_ranges():
    assert _has_temporal_coverage(["2024-05-10"], "2024-01-01..*") is True
    assert _has_temporal_coverage(["2023-05-10"], "2024-01-01..*") is False


def test_research_uses_standard_llm_tool_decision_when_coverage_is_strong():
    """The standard agent tool call should reach synthesis without a relevance grader."""
    call_count = 0

    @tool
    def search_tweets(query: str, **kwargs) -> str:
        """Return strong multi-author evidence for the test query."""
        nonlocal call_count
        call_count += 1
        return (
            '<tweet id="tweet:1" author="@one" date="2024-05-10" sentiment="bullish">GGAL sube.</tweet>'
            '<tweet id="tweet:2" author="@two" date="2024-05-11" sentiment="bearish">GGAL enfrenta riesgos.</tweet>'
            '<tweet id="tweet:3" author="@three" date="2024-05-12">GGAL presenta resultados.</tweet>'
        )

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="Sintesis grounded sobre GGAL.")
    mock_bound_llm = MagicMock()
    mock_bound_llm.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{"name": "search_tweets", "args": {"query": "GGAL balance"}, "id": "call_1"}],
    )
    mock_llm.bind_tools.return_value = mock_bound_llm
    graph = build_agent_workflow(search_tool=search_tweets)

    final_state = graph.invoke(
        {"messages": [{"role": "user", "content": "Que dicen de GGAL?"}]},
        config={"configurable": {"llm": mock_llm, "search_tool": search_tweets}},
    )

    assert call_count == 1
    mock_llm.bind_tools.assert_called_once()
    mock_llm.with_structured_output.assert_not_called()
    assert final_state.get("synthesis_calls") == 1
    assert final_state["response"] == "Sintesis grounded sobre GGAL."


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
    assert '<tweet author="@bull_market"' in result
    assert "</tweet>" in result
    assert "ganancias record" in result


def test_query_rewriter_alias_expansion():
    """Valida que el optimizador de query expanda alias comunes como 'la gallega'."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "GGAL Grupo Financiero Galicia balance perspectivas"
    mock_llm.invoke.return_value = mock_response

    state: AgentState = {
        "messages": [HumanMessage(content="que dicen de la gallega hoy")],
        "search_attempts": 0,
        "search_filters": {"user_handles": ["analista"]},
    }
    config = {"configurable": {"llm": mock_llm}}

    result = _rewrite_query(state, config)
    rewritten = result["rewritten_query"]

    assert "GGAL" in rewritten.upper() or "GALICIA" in rewritten.upper()
    assert result["search_attempts"] == 1
    assert result["messages"][0].tool_calls[0]["args"]["user_handles"] == ["analista"]


def test_query_rewriter_date_no_ticker_hallucination():
    """Valida que el optimizador no convierta años en tickers inexistentes (ej: 2024 -> GD24)."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "bonos soberanos en dolares proyeccion 2024"
    mock_llm.invoke.return_value = mock_response

    state: AgentState = {
        "messages": [HumanMessage(content="vision de los bonos soberanos en 2024")],
        "search_attempts": 0,
    }
    config = {"configurable": {"llm": mock_llm}}

    result = _rewrite_query(state, config)
    rewritten = result["rewritten_query"]

    assert "GD24" not in rewritten.upper()
    assert "AL24" not in rewritten.upper()


def test_agent_node_applies_client_search_filters():
    """Valida que los filtros del panel se apliquen a la llamada de busqueda."""
    search_tool = MagicMock()
    mock_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_bound_llm.invoke.return_value = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_tweets",
                "args": {"query": "bonos soberanos"},
                "id": "call_filtered",
            }
        ],
    )
    mock_llm.bind_tools.return_value = mock_bound_llm

    result = _agent_node(
        {
            "messages": [HumanMessage(content="Que dicen de los bonos?")],
            "search_filters": {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "user_handles": ["@analista"],
            },
        },
        {"configurable": {"llm": mock_llm, "search_tool": search_tool}},
    )

    args = result["messages"][0].tool_calls[0]["args"]
    assert args["start_date"] == "2025-01-01"
    assert args["end_date"] == "2025-12-31"
    assert args["user_handles"] == ["analista"]


def test_agent_node_excludes_orphaned_tool_messages_from_decision_context():
    """Evita reenviar resultados de retrieval sin su AIMessage(tool_calls) precedente."""
    search_tool = MagicMock()
    mock_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_bound_llm.invoke.return_value = AIMessage(content="Nueva respuesta")
    mock_llm.bind_tools.return_value = mock_bound_llm

    _agent_node(
        {
            "messages": [
                HumanMessage(content="Consulta anterior"),
                AIMessage(content="Respuesta anterior"),
                ToolMessage(content="Resultado persistido", tool_call_id="missing-call"),
                HumanMessage(content="Nueva consulta"),
            ],
        },
        {"configurable": {"llm": mock_llm, "search_tool": search_tool}},
    )

    decision_messages = mock_bound_llm.invoke.call_args.args[0]
    assert [message.type for message in decision_messages] == ["system", "human", "ai", "human"]
    assert all(message.type != "tool" for message in decision_messages)


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

    assert "conversation_summary" in result
    assert "bonos soberanos" in result["conversation_summary"]
    assert "messages" in result
    # Debe haber 12 RemoveMessage (15 - 3 = 12 viejos)
    removes = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
    assert len(removes) == 12
    assert removes[0].id == "msg_0"
    assert removes[-1].id == "msg_11"


def test_maybe_summarize_excludes_retrieval_payloads_from_conversation_memory():
    """Los tweets recuperados no deben entrar en el resumen conversacional."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = "El usuario consulto por GGAL."
    mock_llm.invoke.return_value = mock_resp

    messages = [
        HumanMessage(content="Que dicen de GGAL?", id="msg_1"),
        ToolMessage(content="<tweet id='tweet:1'>Comprar GGAL ya</tweet>", tool_call_id="call_1"),
        AIMessage(
            content="Los tweets muestran opiniones divididas.",
            id="msg_2",
        ),
        HumanMessage(content="Y que riesgos mencionan?", id="msg_3"),
    ]
    result = _maybe_summarize(
        {"messages": messages},
        {"configurable": {"llm": mock_llm, "memory_token_limit": 1, "memory_keep_messages": 1}},
    )

    summary_input = mock_llm.invoke.call_args.args[0][1].content
    assert "Que dicen de GGAL?" in summary_input
    assert "opiniones divididas" in summary_input
    assert "Comprar GGAL ya" not in summary_input
    assert "conversation_summary" in result
    assert "summary" not in result


def test_synthesis_context_uses_only_latest_retrieval_attempt():
    messages = [
        HumanMessage(content="Que dicen de GGAL?"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_tweets", "args": {"query": "GGAL"}, "id": "call_1"}],
        ),
        ToolMessage(content="<tweet id='tweet:old'>Resultado descartado</tweet>", tool_call_id="call_1"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_tweets", "args": {"query": "Grupo Galicia"}, "id": "call_2"}],
        ),
        ToolMessage(content="<tweet id='tweet:new'>Resultado final</tweet>", tool_call_id="call_2"),
    ]

    context = _synthesis_context_messages(messages)
    context_text = "\n".join(str(getattr(message, "content", "")) for message in context)

    assert "Resultado final" in context_text
    assert "Resultado descartado" not in context_text
    assert context[-2].tool_calls[0]["id"] == "call_2"
    assert context[-1].tool_call_id == "call_2"


def test_relevance_check_records_deterministic_evidence_quality():
    from agent.src.workflows.crag import RelevanceResult

    mock_llm = MagicMock()
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = RelevanceResult(
        score=8,
        reason="Evidencia pertinente.",
    )
    mock_llm.with_structured_output.return_value = structured_llm

    result = _check_relevance(
        {
            "messages": [
                HumanMessage(content="Que dicen de GGAL?"),
                ToolMessage(
                    content=(
                        '<tweet id="tweet:1" author="@a" date="2026-01-01" sentiment="bullish">Sube</tweet>\n'
                        '<tweet id="tweet:2" author="@b" date="2026-01-02" sentiment="bearish">Riesgo</tweet>'
                    ),
                    tool_call_id="call_1",
                ),
            ]
        },
        {"configurable": {"llm": mock_llm}},
    )

    quality = result["evidence_quality"]
    assert quality["document_count"] == 2
    assert quality["unique_authors"] == 2
    assert quality["contradiction_detected"] is True
    assert quality["coverage"] == "partial"


def test_standard_synthesis_uses_xml_evidence_context():
    from agent.src.workflows.crag import _synthesize

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="GGAL tuvo opiniones divididas [evidence:tweet:known].")

    result = _synthesize(
        {
            "messages": [
                HumanMessage(content="Que dicen de GGAL?"),
                ToolMessage(
                    content='<tweet id="tweet:known" author="@a" date="2026-01-01">GGAL</tweet>',
                    tool_call_id="call_1",
                ),
            ]
        },
        {"configurable": {"llm": mock_llm}},
    )

    assert result["response"] == "GGAL tuvo opiniones divididas [evidence:tweet:known]."
    assert result["citation_audit"]["status"] == "complete"
    assert result["citation_audit"]["valid_citations"] == ["tweet:known"]
    prompt_messages = mock_llm.invoke.call_args.args[0]
    assert '<tweet id="tweet:known"' in prompt_messages[-1].content
    mock_llm.with_structured_output.assert_not_called()


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


def test_relevance_check_uses_latest_user_query():
    """La evaluacion debe usar la pregunta actual y no la primera del hilo."""
    from agent.src.workflows.crag import RelevanceResult

    mock_llm = MagicMock()
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = RelevanceResult(
        score=8,
        reason="La evidencia responde a la pregunta actual.",
    )
    mock_llm.with_structured_output.return_value = structured_llm

    result = _check_relevance(
        {
            "messages": [
                HumanMessage(content="Que paso con AL30?"),
                AIMessage(content="Respuesta anterior"),
                HumanMessage(content="Que dicen ahora de GGAL?"),
                ToolMessage(content="<tweet>GGAL sube</tweet>", tool_call_id="call_1"),
            ]
        },
        {"configurable": {"llm": mock_llm}},
    )

    evaluation_text = structured_llm.invoke.call_args.args[0][1].content
    assert 'Consulta del usuario: "Que dicen ahora de GGAL?"' in evaluation_text
    assert "AL30" not in evaluation_text.split("Consulta del usuario:", 1)[1].split("\n", 1)[0]
    assert result["relevance_evaluation_degraded"] is False


def test_relevance_check_marks_evaluation_failure_as_degraded():
    """Un fallo del juez no debe convertirse en un falso resultado relevante."""
    mock_llm = MagicMock()
    structured_llm = MagicMock()
    structured_llm.invoke.side_effect = RuntimeError("judge unavailable")
    mock_llm.with_structured_output.return_value = structured_llm

    result = _check_relevance(
        {
            "messages": [
                HumanMessage(content="Que dicen de GGAL?"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_tweets", "args": {"query": "GGAL"}, "id": "call_1"}],
                ),
                ToolMessage(content="<tweet>GGAL sube</tweet>", tool_call_id="call_1"),
            ]
        },
        {"configurable": {"llm": mock_llm}},
    )

    assert result["relevance_score"] == 0.0
    assert result["relevance_evaluation_degraded"] is True


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
    agent -> tools (intento 1 sin resultados) -> rewrite_query
    -> tools (intento 2 ambiguo) -> check_relevance (score 9) -> synthesize -> END.
    """
    from agent.src.workflows.crag import RelevanceResult

    call_count = 0

    @tool
    def search_tweets(query: str, **kwargs) -> str:
        """Herramienta mock de busqueda de tweets."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ""
        return '<tweet id="tweet:ggal" author="@inversor" date="2024-05-10">Excelente balance de $GGAL con ganancias solidas.</tweet>'

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
        return RelevanceResult(score=9, reason="Tweets financieros directamente sobre GGAL.")

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
        "messages": [{"role": "user", "content": "Que dicen de GGAL?"}],
    }

    final_state = agent_graph.invoke(initial_state, config=config)

    assert call_count == 2, f"Se esperaban 2 llamadas a la tool pero hubo {call_count}"
    assert structured_call_count == 1, f"Se esperaba 1 evaluacion ambigua pero hubo {structured_call_count}"
    assert final_state.get("relevance_score") == 9.0
    assert final_state.get("synthesis_calls") == 1
    assert "excelente balance de GGAL" in final_state.get("response", "")

    tool_messages = [m for m in final_state["messages"] if getattr(m, "type", None) == "tool"]
    assert len(tool_messages) == 2


def test_entrypoint_rate_limiting(monkeypatch):
    """Valida que el middleware aplique cuota global en DynamoDB para demo y permita bypass para admin."""
    import base64
    import json

    from agent.src import entrypoint
    from agent.src.config import AppConfig
    from fastapi.testclient import TestClient

    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "3")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@fintwit.com")
    monkeypatch.setattr(entrypoint, "app_config", AppConfig.from_env())

    # Mock DynamoDB table store
    mock_db: dict[str, dict] = {}

    class MockDynamoTable:
        def get_item(self, Key, ConsistentRead=False):
            pk = Key.get("PK")
            item = mock_db.get(pk)
            return {"Item": item} if item else {}

        def put_item(self, Item):
            pk = Item.get("PK")
            mock_db[pk] = Item
            return {}

    mock_table = MockDynamoTable()
    monkeypatch.setattr(entrypoint.rate_limiter, "_table", mock_table)

    mock_clone = MagicMock()

    async def mock_run(data):
        if False:
            yield None

    mock_clone.run = mock_run
    monkeypatch.setattr(entrypoint.langgraph_agent, "clone", MagicMock(return_value=mock_clone))

    client = TestClient(entrypoint.app)

    # Healthchecks no deben ser rate-limited
    for _ in range(5):
        resp = client.get("/ping")
        assert resp.status_code == 200

    # Crear token demo y token admin simulados
    demo_payload = base64.urlsafe_b64encode(json.dumps({"username": "demo@fintwit.com"}).encode()).decode()
    demo_auth = f"Bearer header.{demo_payload}.sig"

    admin_payload = base64.urlsafe_b64encode(json.dumps({"username": "admin@fintwit.com"}).encode()).decode()
    admin_auth = f"Bearer header.{admin_payload}.sig"

    # Invocaciones demo estándar (3 permitidas)
    for i in range(3):
        resp = client.post(
            "/invocations",
            headers={"Authorization": demo_auth},
            json={
                "threadId": "test-rl",
                "runId": f"run-{i}",
                "messages": [{"role": "user", "content": "hola", "id": f"msg-{i}"}],
            },
        )
        assert resp.status_code != 429, f"El request {i + 1} no debio ser bloqueado"

    # 4to request demo debe ser bloqueado con HTTP 429
    blocked_resp = client.post(
        "/invocations",
        headers={"Authorization": demo_auth},
        json={
            "threadId": "test-rl",
            "runId": "run-blocked",
            "messages": [{"role": "user", "content": "hola", "id": "msg-blocked"}],
        },
    )
    assert blocked_resp.status_code == 429
    data = blocked_resp.json()
    assert data["error"] == "Rate limit exceeded"
    assert "retry_after_seconds" in data

    # Peticiones admin deben pasar ilimitadamente (bypass)
    for i in range(5):
        admin_resp = client.post(
            "/invocations",
            headers={"Authorization": admin_auth},
            json={
                "threadId": "test-admin",
                "runId": f"admin-run-{i}",
                "messages": [{"role": "user", "content": "consulta admin", "id": f"admin-msg-{i}"}],
            },
        )
        assert admin_resp.status_code != 429, f"El request admin {i + 1} debio tener bypass de rate limit"


def test_entrypoint_input_length_limit(monkeypatch):
    """Verifica que mensajes de usuario mayores a max_input_chars sean rechazados con HTTP 400."""
    from agent.src import entrypoint
    from agent.src.config import AppConfig

    monkeypatch.setenv("MAX_INPUT_CHARS", "50")
    monkeypatch.setattr(entrypoint, "app_config", AppConfig.from_env())

    mock_clone = MagicMock()

    async def mock_run(data):
        if False:
            yield None

    mock_clone.run = mock_run
    monkeypatch.setattr(entrypoint.langgraph_agent, "clone", MagicMock(return_value=mock_clone))

    client = TestClient(entrypoint.app)

    # Mensaje normal <= 50 chars pasa validacion
    ok_resp = client.post(
        "/invocations",
        json={"threadId": "t1", "runId": "r1", "messages": [{"role": "user", "content": "hola corto", "id": "m1"}]},
    )
    assert ok_resp.status_code != 400

    # Mensaje largo > 50 chars es rechazado
    long_msg = "X" * 51
    bad_resp = client.post(
        "/invocations",
        json={"threadId": "t1", "runId": "r2", "messages": [{"role": "user", "content": long_msg, "id": "m2"}]},
    )
    assert bad_resp.status_code == 400
    assert bad_resp.json()["error"] == "Input length exceeded"


def test_entrypoint_thread_turn_limit(monkeypatch):
    """Verifica que hilos con mas de max_thread_turns sean rechazados con HTTP 400."""
    from agent.src import entrypoint
    from agent.src.config import AppConfig

    monkeypatch.setenv("MAX_THREAD_TURNS", "3")
    monkeypatch.setattr(entrypoint, "app_config", AppConfig.from_env())

    mock_clone = MagicMock()

    async def mock_run(data):
        if False:
            yield None

    mock_clone.run = mock_run
    monkeypatch.setattr(entrypoint.langgraph_agent, "clone", MagicMock(return_value=mock_clone))

    client = TestClient(entrypoint.app)

    # Conversacion con 3 turnos pasa
    messages_3 = [{"role": "user", "content": f"msg {i}", "id": f"m{i}"} for i in range(3)]
    ok_resp = client.post("/invocations", json={"threadId": "t1", "runId": "r1", "messages": messages_3})
    assert ok_resp.status_code != 400

    # Conversacion con 4 turnos es rechazada
    messages_4 = [{"role": "user", "content": f"msg {i}", "id": f"m{i}"} for i in range(4)]
    bad_resp = client.post("/invocations", json={"threadId": "t1", "runId": "r2", "messages": messages_4})
    assert bad_resp.status_code == 400
    assert bad_resp.json()["error"] == "Thread limit reached"


def test_entrypoint_cors_headers():
    """Verifica que FastAPI responda con los headers CORS adecuados ante preflight OPTIONS."""
    from agent.src import entrypoint

    client = TestClient(entrypoint.app)
    resp = client.options(
        "/invocations",
        headers={
            "Origin": "https://rag.fintwit.com.ar",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://rag.fintwit.com.ar"


def test_format_tweet_doc_xml_tags():
    """Verifica que format_tweet_doc genere tags XML delimitados y sanitice breakouts."""
    from agent.src.vector_store import format_tweet_doc
    from langchain_core.documents import Document

    doc = Document(
        page_content="Comprando <tweet>GGAL</tweet> a full",
        metadata={
            "evidence_id": "tweet:123",
            "user_handle": "trader_arg",
            "tweet_timestamp": "2024-03-15T12:00:00Z",
            "url": "https://x.com/trader_arg/status/123",
        },
    )
    formatted = format_tweet_doc(doc)
    assert formatted.startswith('<tweet author="@trader_arg" date="2024-03-15" id="tweet:123"')
    assert 'url="https://x.com/trader_arg/status/123"' in formatted
    assert formatted.endswith("</tweet>")
    # Tags internos sanitizados para prevenir escape
    assert "<tweet>GGAL</tweet>" not in formatted
