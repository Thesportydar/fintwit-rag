from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated, Any, TypedDict

logger = logging.getLogger(__name__)

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field

from ..citation_audit import audit_citations
from ..evidence_quality import format_evidence_quality, grade_evidence, parse_formatted_evidence

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_AGENT_PROMPT = (_PROMPTS_DIR / "agent_prompt.txt").read_text(encoding="utf-8").strip()
_SYNTHESIZE_PROMPT = (_PROMPTS_DIR / "synthesize_prompt.txt").read_text(encoding="utf-8").strip()
_SUMMARIZE_PROMPT = (_PROMPTS_DIR / "summarize_prompt.txt").read_text(encoding="utf-8").strip()
_RELEVANCE_CHECK_PROMPT = (_PROMPTS_DIR / "relevance_check_prompt.txt").read_text(encoding="utf-8").strip()
_QUERY_REWRITE_PROMPT = (_PROMPTS_DIR / "query_rewrite_prompt.txt").read_text(encoding="utf-8").strip()


class RelevanceResult(BaseModel):
    score: int = Field(description="Score de relevancia de 0 a 10")
    reason: str = Field(description="Breve justificacion del score asignado")


class AgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    conversation_summary: str
    search_filters: dict[str, Any]
    rewritten_query: str
    relevance_score: float
    relevance_reason: str
    relevance_evaluation_degraded: bool
    evidence_quality: dict[str, Any]
    coverage_state: str
    retry_reason: str | None
    search_attempts: int
    synthesis_calls: int
    response: str
    citation_audit: dict[str, Any]


def _search_filters_from_state(state: AgentState) -> dict[str, Any]:
    """Normaliza los filtros estructurados enviados por el cliente."""
    raw_filters = state.get("search_filters")
    if not isinstance(raw_filters, dict):
        return {}

    filters: dict[str, Any] = {}
    list_keys = {"user_handles", "tickers", "topics"}
    allowed_keys = list_keys | {"start_date", "end_date", "sentiment"}

    for key in allowed_keys:
        value = raw_filters.get(key)
        if key in list_keys:
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list):
                continue
            cleaned = [str(item).strip().lstrip("@") for item in value if str(item).strip()]
            if cleaned:
                filters[key] = cleaned
        elif isinstance(value, str) and value.strip():
            filters[key] = value.strip()

    return filters


def _apply_search_filters(response: AIMessage, state: AgentState) -> AIMessage:
    """Fuerza los filtros del panel en cada llamada de busqueda del agente."""
    active_filters = _search_filters_from_state(state)
    if not active_filters or not response.tool_calls:
        return response

    tool_calls = []
    for tool_call in response.tool_calls:
        if tool_call.get("name") != "search_tweets":
            tool_calls.append(tool_call)
            continue
        tool_calls.append(
            {
                **tool_call,
                "args": {
                    **tool_call.get("args", {}),
                    **active_filters,
                },
            }
        )

    return response.model_copy(update={"tool_calls": tool_calls})


def _latest_user_query(messages: list[Any]) -> str | None:
    """Return the most recent user message for multi-turn evaluation."""
    for message in reversed(messages):
        if getattr(message, "type", None) in ("human", "user"):
            content = getattr(message, "content", "")
            return content if isinstance(content, str) else str(content)
    return None


def _has_temporal_coverage(document_dates: list[str], temporal_scope: str) -> bool:
    parsed_dates = []
    for value in document_dates:
        try:
            parsed_dates.append(date.fromisoformat(value[:10]))
        except ValueError:
            continue
    if not parsed_dates:
        return False

    start_text, end_text = temporal_scope.split("..", 1)
    start = date.fromisoformat(start_text) if start_text != "*" else None
    end = date.fromisoformat(end_text) if end_text != "*" else None
    return any((start is None or value >= start) and (end is None or value <= end) for value in parsed_dates)


def _conversation_summary(state: AgentState) -> str:
    return str(state.get("conversation_summary") or "")


def _is_conversational_message(message: Any) -> bool:
    """Keep dialogue turns out of memory while excluding retrieval/tool payloads."""
    message_type = getattr(message, "type", None)
    if message_type in ("human", "user"):
        return True
    return message_type == "ai" and not getattr(message, "tool_calls", None)


def _synthesis_context_messages(messages: list[Any]) -> list[Any]:
    """Keep dialogue plus the valid AI/tool pair for the latest retrieval result."""
    latest_tool_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if getattr(messages[index], "type", None) == "tool"),
        None,
    )
    if latest_tool_index is None:
        return [message for message in messages if _is_conversational_message(message)]

    latest_tool = messages[latest_tool_index]
    tool_call_id = getattr(latest_tool, "tool_call_id", None)
    tool_call_message = next(
        (
            message
            for message in reversed(messages[:latest_tool_index])
            if getattr(message, "type", None) == "ai"
            and any(call.get("id") == tool_call_id for call in (getattr(message, "tool_calls", None) or []))
        ),
        None,
    )
    context = [message for message in messages if _is_conversational_message(message)]
    if tool_call_message is not None:
        context.append(tool_call_message)
    if latest_tool is not None:
        context.append(latest_tool)
    return context


def _maybe_summarize(state: AgentState, config: RunnableConfig) -> dict:
    """Comprime el historial de mensajes si supera el limite de tokens."""
    messages = state.get("messages", [])
    token_limit = config.get("configurable", {}).get("memory_token_limit", 4000)
    keep_messages = config.get("configurable", {}).get("memory_keep_messages", 10)

    # Estimacion de tokens: ~4 chars = 1 token
    total_tokens = sum(len(str(getattr(m, "content", m))) for m in messages) // 4

    if total_tokens <= token_limit or len(messages) <= keep_messages:
        return {}

    llm = config["configurable"]["llm"]

    old_messages = messages[:-keep_messages]

    history_lines = []
    existing_summary = _conversation_summary(state)
    if existing_summary:
        history_lines.append(f"RESUMEN PREVIO: {existing_summary}")

    for m in old_messages:
        if not _is_conversational_message(m):
            continue
        role = getattr(m, "type", "msg").upper()
        content = m.content if isinstance(getattr(m, "content", None), str) else str(getattr(m, "content", m))
        history_lines.append(f"{role}: {content}")

    history_text = "\n".join(history_lines)

    summary_response = llm.invoke(
        [
            SystemMessage(content=_SUMMARIZE_PROMPT),
            HumanMessage(content=f"Resume esta conversacion:\n\n{history_text}"),
        ],
        config={
            **config,
            "tags": config.get("tags", []) + ["summarize", "hide_stream"],
            "metadata": {**config.get("metadata", {}), "emit-messages": False, "emit-tool-calls": False},
        },
    )

    summary_content = summary_response.content
    if isinstance(summary_content, list):
        summary_content = " ".join(
            b.get("text", "") for b in summary_content if isinstance(b, dict) and b.get("type") == "text"
        )
    elif not isinstance(summary_content, str):
        summary_content = str(summary_content)

    removes = [RemoveMessage(id=m.id) for m in old_messages if getattr(m, "id", None)]
    return {
        "conversation_summary": summary_content.strip(),
        "messages": removes,
    }


def _agent_node(state: AgentState, config: RunnableConfig) -> dict:
    """Decide si responder directamente o invocar search_tweets mediante ToolNode."""
    llm = config["configurable"]["llm"]
    search_tool = config["configurable"]["search_tool"]

    bound_llm = llm.bind_tools([search_tool], parallel_tool_calls=False)
    messages = state.get("messages", [])

    agent_system = _AGENT_PROMPT
    summary = _conversation_summary(state)
    if summary:
        agent_system = f"{agent_system}\n\n[RESUMEN DE CONVERSACION PREVIA]\n{summary}"

    # Los resultados de retrieval no forman parte del contexto de decision.
    # Excluirlos tambien evita reenviar ToolMessage huerfanos desde checkpoints
    # o snapshots AG-UI que no conservaron su AIMessage(tool_calls).
    formatted_messages = [SystemMessage(content=agent_system)] + [
        message for message in messages if _is_conversational_message(message)
    ]
    response = bound_llm.invoke(
        formatted_messages,
        config={**config, "tags": config.get("tags", []) + ["agent_decision"]},
    )

    response = _apply_search_filters(response, state)
    result = {"messages": [response]}
    if response.tool_calls:
        result["search_attempts"] = state.get("search_attempts", 0) + 1
    return result


def _check_relevance(state: AgentState, config: RunnableConfig) -> dict:
    """Evalua la relevancia de los fragmentos de tweets recuperados por la tool search_tweets."""
    messages = state.get("messages", [])

    # Obtener el ultimo ToolMessage emitido por search_tweets
    last_tool_msg = next((m for m in reversed(messages) if getattr(m, "type", None) == "tool"), None)
    tool_content = _message_content(last_tool_msg)

    attempt = state.get("search_attempts", 1)

    # Si la herramienta no devolvio tweets
    if not tool_content.strip() or "no se encontraron tweets" in tool_content.lower():
        return {
            "relevance_score": 0.0,
            "relevance_reason": "La herramienta no encontro tweets para la busqueda.",
            "relevance_evaluation_degraded": False,
            "evidence_quality": grade_evidence([]).model_dump(),
            "search_attempts": attempt,
        }

    llm = config["configurable"]["llm"]

    # Encontrar la consulta original del usuario
    user_query = _latest_user_query(messages)
    if not user_query:
        user_query = "consulta general"

    # Determinar la query utilizada en la busqueda
    query_used = state.get("rewritten_query")
    if not query_used:
        for m in reversed(messages):
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    if tc.get("name") == "search_tweets" and "query" in tc.get("args", {}):
                        query_used = tc["args"]["query"]
                        break
            if query_used:
                break
    if not query_used:
        query_used = user_query

    eval_msg = (
        f'Consulta del usuario: "{user_query}"\n'
        f'Query utilizada en la busqueda: "{query_used}"\n\n'
        f"Fragmentos de tweets recuperados:\n{tool_content[:2000]}"
    )

    try:
        structured_llm = llm.with_structured_output(RelevanceResult)
        # Excluir callbacks para que el JSON de evaluacion interna no se emita al stream SSE del usuario
        result: RelevanceResult = structured_llm.invoke(
            [
                SystemMessage(content=_RELEVANCE_CHECK_PROMPT),
                HumanMessage(content=eval_msg),
            ],
            config={
                **config,
                "tags": ["crag_relevance_check"],
                "metadata": {**config.get("metadata", {}), "emit-messages": False, "emit-tool-calls": False},
            },
        )
        return {
            "relevance_score": float(result.score),
            "relevance_reason": result.reason,
            "relevance_evaluation_degraded": False,
            "evidence_quality": grade_evidence(parse_formatted_evidence(tool_content)).model_dump(),
            "search_attempts": attempt,
        }
    except Exception as exc:
        logger.warning("CRAG relevance check fallo; se marca la evaluacion como degradada: %s", exc)
        return {
            "relevance_score": 0.0,
            "relevance_reason": f"No se pudo evaluar la relevancia: {exc}",
            "relevance_evaluation_degraded": True,
            "evidence_quality": grade_evidence(parse_formatted_evidence(tool_content)).model_dump(),
            "search_attempts": attempt,
        }


def _message_content(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def _latest_tool_content(messages: list[Any]) -> str:
    last_tool_msg = next((message for message in reversed(messages) if getattr(message, "type", None) == "tool"), None)
    return _message_content(last_tool_msg)


def _assess_coverage(state: AgentState) -> dict:
    """Assess retrieval sufficiency without an LLM before paying for a grader."""

    documents = parse_formatted_evidence(_latest_tool_content(state.get("messages", [])))
    quality = grade_evidence(documents).model_dump()
    filters = _search_filters_from_state(state)
    recoverable_reason: str | None = None

    if not documents:
        coverage_state = "insufficient"
        recoverable_reason = "no_results"
    else:
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        temporal_scope = f"{start_date or '*'}..{end_date or '*'}" if start_date or end_date else None
        date_values = [document.get("date", "") for document in documents if document.get("date")]
        if temporal_scope and not _has_temporal_coverage(date_values, temporal_scope):
            recoverable_reason = "missing_temporal_coverage"

        requested_handles = filters.get("user_handles", [])
        enough_authors = quality["unique_authors"] >= 2 or bool(requested_handles)
        enough_documents = quality["document_count"] >= 3
        if recoverable_reason:
            coverage_state = "insufficient"
        elif enough_documents and enough_authors:
            coverage_state = "sufficient"
        else:
            coverage_state = "ambiguous"

    return {
        "coverage_state": coverage_state,
        "retry_reason": recoverable_reason,
        "evidence_quality": quality,
    }


def _route_after_coverage(state: AgentState, config: RunnableConfig) -> str:
    """Choose synthesis, optional grading, or a recoverable retry."""
    coverage_state = state.get("coverage_state", "insufficient")
    if coverage_state == "sufficient":
        return "synthesize"
    if coverage_state == "ambiguous":
        return "check_relevance"
    max_attempts = config.get("configurable", {}).get("max_attempts", 2)
    if state.get("search_attempts", 0) >= max_attempts:
        return "synthesize"
    return "rewrite_query"


def _route_after_check(state: AgentState, config: RunnableConfig) -> str:
    """Retry only weak, recoverable evidence; otherwise synthesize once."""
    score = state.get("relevance_score", 0.0)
    attempts = state.get("search_attempts", 1)
    threshold = config.get("configurable", {}).get("relevance_threshold", 5.0)
    max_attempts = config.get("configurable", {}).get("max_attempts", 2)

    if (
        score >= threshold
        or attempts >= max_attempts
        or state.get("retry_reason") not in {"no_results", "missing_temporal_coverage"}
    ):
        return "synthesize"
    return "rewrite_query"


def _rewrite_query(state: AgentState, config: RunnableConfig) -> dict:
    """Reformula la query correctivamente y emite un nuevo tool call para ToolNode."""
    llm = config["configurable"]["llm"]
    messages = state.get("messages", [])
    attempt = state.get("search_attempts", 1)

    # Identificar la consulta original del usuario
    original_query = _latest_user_query(messages)
    if not original_query:
        original_query = "consulta financiera"

    prev_query = state.get("rewritten_query")
    if not prev_query:
        for m in reversed(messages):
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    if tc.get("name") == "search_tweets" and "query" in tc.get("args", {}):
                        prev_query = tc["args"]["query"]
                        break
            if prev_query:
                break
    if not prev_query:
        prev_query = original_query

    prev_reason = state.get("relevance_reason", "")

    reason_ctx = f'\nMotivo de descarte de resultados anteriores: "{prev_reason}"' if prev_reason else ""
    user_msg = (
        f'Consulta original: "{original_query}"\n'
        f'INTENTO {attempt + 1}. La busqueda anterior con query "{prev_query}" no obtuvo resultados relevantes.\n'
        f"{reason_ctx}\n"
        "Reformula la query para encontrar tweets pertinentes sobre el tema sin inventar datos ni tickers."
    )

    response = llm.invoke(
        [
            SystemMessage(content=_QUERY_REWRITE_PROMPT),
            HumanMessage(content=user_msg),
        ],
        config={
            **config,
            "tags": ["crag_rewrite"],
            "metadata": {**config.get("metadata", {}), "emit-messages": False, "emit-tool-calls": False},
        },
    )

    content = response.content
    if isinstance(content, list):
        text_blocks = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = " ".join(text_blocks)
    elif not isinstance(content, str):
        content = str(content)

    rewritten = content.strip().strip('"').strip("'") or original_query

    call_id = f"call_{uuid.uuid4().hex[:8]}"
    retry_tool_call = AIMessage(
        content=f"Reintentando busqueda con query optimizada: '{rewritten}'",
        tool_calls=[
            {
                "name": "search_tweets",
                "args": {"query": rewritten, **_search_filters_from_state(state)},
                "id": call_id,
            }
        ],
    )

    return {
        "rewritten_query": rewritten,
        "messages": [retry_tool_call],
        "search_attempts": attempt + 1,
    }


def _synthesize(state: AgentState, config: RunnableConfig) -> dict:
    """Sintetiza la respuesta final del analista a partir de los resultados de la herramienta."""
    llm = config["configurable"]["llm"]
    messages = state.get("messages", [])

    synth_system = _SYNTHESIZE_PROMPT
    summary = _conversation_summary(state)
    if summary:
        synth_system = f"{synth_system}\n\n[RESUMEN DE CONVERSACION PREVIA]\n{summary}"

    relevance_score = state.get("relevance_score")
    if relevance_score is not None:
        relevance_reason = state.get("relevance_reason") or ""
        crag_meta = f"\n\n[EVALUACION CRAG: Relevancia {relevance_score}/10 | {relevance_reason}]"
        synth_system = f"{synth_system}{crag_meta}"
    if state.get("relevance_evaluation_degraded"):
        synth_system = (
            f"{synth_system}\n\nLa evaluacion automatica de relevancia fallo. "
            "Trata la evidencia como potencialmente insuficiente y explicita esa limitacion."
        )
    evidence_quality = state.get("evidence_quality")
    if evidence_quality:
        synth_system = f"{synth_system}\n\n[CALIDAD DE EVIDENCIA]\n{format_evidence_quality(evidence_quality)}"

    synth_messages: list[Any] = [SystemMessage(content=synth_system)] + _synthesis_context_messages(messages)

    response = llm.invoke(
        synth_messages,
        config={**config, "tags": config.get("tags", []) + ["agent_synthesis"]},
    )
    citation_audit = audit_citations(_message_content(response), _latest_tool_content(messages))

    return {
        "messages": [response],
        "response": response.content,
        "citation_audit": citation_audit,
        "synthesis_calls": state.get("synthesis_calls", 0) + 1,
    }


def build_agent_workflow(
    search_tool: Any = None,
    checkpointer: Any = None,
    store: Any = None,
) -> Any:
    """Compile standard tool calling, retrieval gating, optional grading, and one synthesis."""
    if search_tool is None:
        from langchain_core.tools import tool

        @tool
        def search_tweets(query: str, **kwargs) -> str:
            """Herramienta de busqueda de tweets por defecto."""
            return "No se encontraron tweets relevantes para la busqueda."

        search_tool = search_tweets

    builder = StateGraph(AgentState)

    builder.add_node("maybe_summarize", _maybe_summarize)
    builder.add_node("agent_node", _agent_node)
    builder.add_node("tools", ToolNode([search_tool]))
    builder.add_node("assess_coverage", _assess_coverage)
    builder.add_node("check_relevance", _check_relevance)
    builder.add_node("rewrite_query", _rewrite_query)
    builder.add_node("synthesize", _synthesize)

    builder.add_edge(START, "maybe_summarize")
    builder.add_edge("maybe_summarize", "agent_node")
    builder.add_conditional_edges(
        "agent_node",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "assess_coverage")
    builder.add_conditional_edges(
        "assess_coverage",
        _route_after_coverage,
        {
            "synthesize": "synthesize",
            "check_relevance": "check_relevance",
            "rewrite_query": "rewrite_query",
        },
    )
    builder.add_conditional_edges(
        "check_relevance",
        _route_after_check,
        {
            "synthesize": "synthesize",
            "rewrite_query": "rewrite_query",
        },
    )
    builder.add_edge("rewrite_query", "tools")
    builder.add_edge("synthesize", END)

    return builder.compile(checkpointer=checkpointer, store=store)
