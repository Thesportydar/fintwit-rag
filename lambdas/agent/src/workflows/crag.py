from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, Any, TypedDict

logger = logging.getLogger(__name__)

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_AGENT_PROMPT = (_PROMPTS_DIR / "agent_prompt.txt").read_text(encoding="utf-8").strip()
_SYNTHESIZE_PROMPT = (_PROMPTS_DIR / "synthesize_prompt.txt").read_text(encoding="utf-8").strip()
_SUMMARIZE_PROMPT = (_PROMPTS_DIR / "summarize_prompt.txt").read_text(encoding="utf-8").strip()
_RELEVANCE_CHECK_PROMPT = (_PROMPTS_DIR / "relevance_check_prompt.txt").read_text(encoding="utf-8").strip()
_QUERY_REWRITE_PROMPT = (_PROMPTS_DIR / "query_rewrite_prompt.txt").read_text(encoding="utf-8").strip()


class RelevanceResult(BaseModel):
    score: int = Field(description="Score de relevancia de 0 a 10")
    relevant: bool = Field(description="True si el score es >= 5")
    reason: str = Field(description="Breve justificacion del score asignado")


class AgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    summary: str
    query: str
    start_date: str | None
    end_date: str | None
    tickers: list[str]
    sentiment: str | None
    topics: list[str]
    user_handles: list[str]
    rewritten_query: str
    documents: list[Any]
    relevance_score: float
    is_relevant: bool
    relevance_reason: str
    search_attempts: int
    final_evidence: str
    response: str


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
    existing_summary = state.get("summary")
    if existing_summary:
        history_lines.append(f"RESUMEN PREVIO: {existing_summary}")

    for m in old_messages:
        role = getattr(m, "type", "msg").upper()
        content = m.content if isinstance(getattr(m, "content", None), str) else str(getattr(m, "content", m))
        history_lines.append(f"{role}: {content}")

    history_text = "\n".join(history_lines)

    summary_response = llm.invoke(
        [
            SystemMessage(content=_SUMMARIZE_PROMPT),
            HumanMessage(content=f"Resume esta conversacion:\n\n{history_text}"),
        ],
        config={**config, "tags": config.get("tags", []) + ["summarize", "hide_stream"]},
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
        "summary": summary_content.strip(),
        "messages": removes,
    }


def _agent_node(state: AgentState, config: RunnableConfig) -> dict:
    """Decide si responder directamente o invocar search_tweets mediante ToolNode."""
    llm = config["configurable"]["llm"]
    search_tool = config["configurable"]["search_tool"]

    bound_llm = llm.bind_tools([search_tool], parallel_tool_calls=False)
    messages = state.get("messages", [])

    agent_system = _AGENT_PROMPT
    summary = state.get("summary")
    if summary:
        agent_system = f"{agent_system}\n\n[RESUMEN DE CONVERSACION PREVIA]\n{summary}"

    formatted_messages = [SystemMessage(content=agent_system)] + list(messages)
    response = bound_llm.invoke(
        formatted_messages,
        config={**config, "tags": config.get("tags", []) + ["agent_decision"]},
    )

    return {"messages": [response]}


def _check_relevance(state: AgentState, config: RunnableConfig) -> dict:
    """Evalua la relevancia de los fragmentos de tweets recuperados por la tool search_tweets."""
    messages = state.get("messages", [])

    # Obtener el ultimo ToolMessage emitido por search_tweets
    last_tool_msg = next((m for m in reversed(messages) if getattr(m, "type", None) == "tool"), None)
    tool_content = last_tool_msg.content if last_tool_msg else ""
    if isinstance(tool_content, list):
        tool_content = " ".join(
            b.get("text", "") for b in tool_content if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        tool_content = str(tool_content)

    attempt = state.get("search_attempts", 0) + 1

    # Si la herramienta no devolvio tweets
    if not tool_content.strip() or "no se encontraron tweets" in tool_content.lower():
        return {
            "relevance_score": 0.0,
            "is_relevant": False,
            "relevance_reason": "La herramienta no encontro tweets para la busqueda.",
            "search_attempts": attempt,
        }

    llm = config["configurable"]["llm"]

    # Encontrar la consulta original del usuario
    user_query = state.get("query")
    if not user_query:
        for m in messages:
            if getattr(m, "type", None) in ("human", "user"):
                user_query = m.content if isinstance(m.content, str) else str(m.content)
                break
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
        result: RelevanceResult = structured_llm.invoke(
            [
                SystemMessage(content=_RELEVANCE_CHECK_PROMPT),
                HumanMessage(content=eval_msg),
            ],
            config={**config, "tags": config.get("tags", []) + ["crag_relevance_check", "hide_stream"]},
        )
        return {
            "relevance_score": float(result.score),
            "is_relevant": bool(result.relevant),
            "relevance_reason": result.reason,
            "search_attempts": attempt,
        }
    except Exception as exc:
        logger.warning("CRAG relevance check fallo, usando fallback permisivo: %s", exc)
        return {
            "relevance_score": 6.0,
            "is_relevant": True,
            "relevance_reason": f"Evaluacion por defecto (fallback: {exc})",
            "search_attempts": attempt,
        }


def _route_after_check(state: AgentState, config: RunnableConfig) -> str:
    """Decide si proceder a la sintesis o activar reescritura correctiva."""
    score = state.get("relevance_score", 0.0)
    attempts = state.get("search_attempts", 1)
    threshold = config.get("configurable", {}).get("relevance_threshold", 5.0)
    max_attempts = config.get("configurable", {}).get("max_attempts", 2)

    if score >= threshold or attempts >= max_attempts:
        return "synthesize"
    return "rewrite_query"


def _rewrite_query(state: AgentState, config: RunnableConfig) -> dict:
    """Reformula la query correctivamente y emite un nuevo tool call para ToolNode."""
    llm = config["configurable"]["llm"]
    messages = state.get("messages", [])
    attempt = state.get("search_attempts", 1)

    # Identificar la consulta original del usuario
    original_query = state.get("query")
    if not original_query:
        for m in messages:
            if getattr(m, "type", None) in ("human", "user"):
                original_query = m.content if isinstance(m.content, str) else str(m.content)
                break
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
        config={**config, "tags": config.get("tags", []) + ["crag_rewrite", "hide_stream"]},
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
                "args": {"query": rewritten},
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
    summary = state.get("summary")
    if summary:
        synth_system = f"{synth_system}\n\n[RESUMEN DE CONVERSACION PREVIA]\n{summary}"

    relevance_score = state.get("relevance_score")
    if relevance_score is not None:
        relevance_reason = state.get("relevance_reason") or ""
        crag_meta = f"\n\n[EVALUACION CRAG: Relevancia {relevance_score}/10 | {relevance_reason}]"
        synth_system = f"{synth_system}{crag_meta}"

    synth_messages: list[Any] = [SystemMessage(content=synth_system)] + list(messages)

    response = llm.invoke(
        synth_messages,
        config={**config, "tags": config.get("tags", []) + ["agent_synthesis"]},
    )
    return {"messages": [response], "response": response.content}


def build_agent_workflow(
    search_tool: Any = None,
    checkpointer: Any = None,
    store: Any = None,
) -> Any:
    """Compila el grafo unificado CRAG: summarize -> agent_node -> tools -> check_relevance -> synthesize / rewrite."""
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
    builder.add_edge("tools", "check_relevance")
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
