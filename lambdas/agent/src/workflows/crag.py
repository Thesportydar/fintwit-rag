from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from pydantic import BaseModel, Field

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0)


class RelevanceResult(BaseModel):
    score: int = Field(description="Score de relevancia de 0 a 10")
    relevant: bool = Field(description="True si el score es >= 5")
    reason: str = Field(description="Breve justificación del score asignado")


class CRAGState(TypedDict, total=False):
    query: str
    start_date: str | None
    end_date: str | None
    tickers: list[str]
    sentiment: str | None
    topics: list[str]
    rewritten_query: str
    documents: list[Any]
    relevance_score: float
    is_relevant: bool
    relevance_reason: str
    search_attempts: int
    final_evidence: str
    response: str


def _format_doc(d: Document) -> str:
    meta = d.metadata or {}
    handle = meta.get("user_handle", "unknown")
    timestamp = meta.get("tweet_timestamp", "")
    date = timestamp[:10] if timestamp else "unknown"

    parts = [
        "<<< TWEET >>>",
        f"autor: @{handle}",
        f"fecha: {date}",
        f"contenido: {d.page_content}",
        "<<< /TWEET >>>",
    ]
    return "\n".join(parts)


def _rewrite_query(state: CRAGState, config: RunnableConfig) -> dict:
    llm = config["configurable"]["llm"]
    attempt = state.get("search_attempts", 0) + 1
    system_prompt = (_PROMPTS_DIR / "query_rewrite_prompt.txt").read_text(encoding="utf-8").strip()

    original_query = state.get("query", "")
    prev_query = state.get("rewritten_query")
    prev_reason = state.get("relevance_reason")

    if attempt == 1 or not prev_query:
        user_msg = f'Consulta del usuario: "{original_query}"'
    else:
        reason_ctx = f'\nMotivo de descarte de resultados anteriores: "{prev_reason}"' if prev_reason else ""
        user_msg = (
            f'Consulta original: "{original_query}"\n'
            f'INTENTO {attempt}. La búsqueda anterior con query "{prev_query}" no obtuvo resultados relevantes.\n'
            f"{reason_ctx}\n"
            "Reformulá la query para encontrar tweets pertinentes sobre el tema sin inventar datos ni tickers."
        )

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
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

    return {
        "rewritten_query": content.strip() or original_query,
        "search_attempts": attempt,
    }


def _search_and_rerank(state: CRAGState, config: RunnableConfig) -> dict:
    qdrant_client = config["configurable"].get("qdrant_client")
    collection_name = config["configurable"].get("collection_name")
    embeddings = config["configurable"].get("embeddings")
    compressor = config["configurable"]["compressor"]
    k = config["configurable"].get("k", 50)
    qdrant_filter = config["configurable"].get("qdrant_filter")
    query = state.get("rewritten_query") or state.get("query", "")

    search_fn = config["configurable"].get("search_fn")
    if search_fn:
        docs = search_fn(query, filter=qdrant_filter, k=k)
    elif qdrant_client and collection_name and embeddings:
        from ..vector_store import hybrid_search_tweets

        docs = hybrid_search_tweets(
            client=qdrant_client,
            collection_name=collection_name,
            query=query,
            embeddings=embeddings,
            qdrant_filter=qdrant_filter,
            limit=k,
        )
    elif "vectorstore" in config["configurable"]:
        vectorstore = config["configurable"]["vectorstore"]
        search_kwargs = {"k": k}
        if qdrant_filter is not None:
            search_kwargs["filter"] = qdrant_filter
        docs = vectorstore.similarity_search(query, **search_kwargs)
    else:
        docs = []

    if not docs:
        return {
            "documents": [],
            "relevance_score": 0.0,
            "relevance_reason": "No se encontraron documentos en la base de datos para la búsqueda.",
        }

    reranked_docs = compressor.compress_documents(docs, query)
    return {"documents": list(reranked_docs)}


def _check_relevance(state: CRAGState, config: RunnableConfig) -> dict:
    docs = state.get("documents", [])
    if not docs:
        return {
            "relevance_score": 0.0,
            "relevance_reason": "Sin documentos recuperados.",
        }

    llm = config["configurable"]["llm"]
    original_query = state.get("query", "")
    rewritten = state.get("rewritten_query", "")
    system_prompt = (_PROMPTS_DIR / "relevance_check_prompt.txt").read_text(encoding="utf-8").strip()

    snippets = "\n\n".join(
        f"[{i + 1}] @{d.metadata.get('user_handle', 'anon')} ({d.metadata.get('tweet_timestamp', '')[:10]}): {d.page_content[:250]}"
        for i, d in enumerate(docs[:8])
    )
    user_msg = (
        f'Consulta original: "{original_query}"\n'
        f'Query utilizada: "{rewritten}"\n\n'
        f"Fragmentos de tweets recuperados:\n{snippets}"
    )

    try:
        structured_llm = llm.with_structured_output(RelevanceResult)
        result: RelevanceResult = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_msg),
            ],
            config={**config, "tags": config.get("tags", []) + ["crag_relevance_check", "hide_stream"]},
        )
        return {
            "relevance_score": float(result.score),
            "relevance_reason": result.reason,
        }
    except Exception as exc:
        return {
            "relevance_score": 6.0,
            "relevance_reason": f"Evaluación por defecto (error en parser: {exc})",
        }


def _route_after_search(state: CRAGState) -> str:
    if not state.get("documents"):
        return "format_evidence"
    return "check_relevance"


def _route_after_check(state: CRAGState, config: RunnableConfig) -> str:
    score = state.get("relevance_score", 0.0)
    attempts = state.get("search_attempts", 1)
    threshold = config["configurable"].get("relevance_threshold", 5.0)
    max_attempts = config["configurable"].get("max_attempts", 2)

    if score >= threshold or attempts >= max_attempts:
        return "format_evidence"
    return "rewrite_query"


def _format_evidence(state: CRAGState) -> dict:
    docs = state.get("documents", [])
    if not docs:
        msg = "No se encontraron tweets relevantes para la búsqueda solicitada."
        return {"response": msg, "final_evidence": msg}

    serialized = "\n\n".join([_format_doc(d) for d in docs])
    score = state.get("relevance_score")
    if score is not None:
        reason = state.get("relevance_reason") or ""
        header = f"[METADATA CRAG: Relevancia {score}/10 | {reason}]\n\n"
        serialized = header + serialized

    return {"response": serialized, "final_evidence": serialized}


def build_crag_workflow():
    builder = StateGraph(CRAGState)

    builder.add_node("rewrite_query", _rewrite_query)
    builder.add_node("search_and_rerank", _search_and_rerank, retry_policy=_RETRY)
    builder.add_node("check_relevance", _check_relevance)
    builder.add_node("format_evidence", _format_evidence)

    builder.add_edge(START, "rewrite_query")
    builder.add_edge("rewrite_query", "search_and_rerank")
    builder.add_conditional_edges(
        "search_and_rerank",
        _route_after_search,
        ["check_relevance", "format_evidence"],
    )
    builder.add_conditional_edges(
        "check_relevance",
        _route_after_check,
        ["format_evidence", "rewrite_query"],
    )
    builder.add_edge("format_evidence", END)

    return builder.compile(checkpointer=False)
