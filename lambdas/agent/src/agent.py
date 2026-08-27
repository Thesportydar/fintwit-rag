from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from langgraph_checkpoint_aws import DynamoDBSaver
from langgraph_checkpoint_aws.store.dynamodb import DynamoDBStore
from qdrant_client import QdrantClient

from .config import AppConfig
from .embeddings import JinaEmbeddings, JinaRerankCompressor
from .llm import get_llm
from .vector_store import create_search_tweets_tool
from .workflows.crag import build_agent_workflow


@dataclass
class AgentApp:
    graph: Any
    services: dict[str, Any]

    def get_config(
        self,
        thread_id: str = "default_thread",
        extra_configurable: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Combina los servicios base del agente con el thread_id y cualquier configurable extra."""
        return {
            "configurable": {
                **self.services,
                "thread_id": thread_id,
                **(extra_configurable or {}),
            }
        }

    def invoke(
        self,
        messages: list[Any],
        thread_id: str = "default_thread",
        extra_configurable: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ejecuta el grafo del agente con el historial de mensajes y la configuracion resuelta."""
        config = self.get_config(thread_id=thread_id, extra_configurable=extra_configurable)
        return self.graph.invoke({"messages": messages}, config=config)


def create_agent_app(
    app_config: AppConfig | None = None,
    checkpointer: Any = None,
    store: Any = None,
    search_tool: Any = None,
) -> AgentApp:
    """Instancia la infraestructura de servicios y compila el StateGraph del agente."""
    if app_config is None:
        app_config = AppConfig.from_env()

    if app_config.langsmith_tracing:
        os.environ["LANGSMITH_TRACING"] = "true"
        if app_config.langsmith_api_key:
            os.environ["LANGSMITH_API_KEY"] = app_config.langsmith_api_key
        if app_config.langsmith_project:
            os.environ["LANGSMITH_PROJECT"] = app_config.langsmith_project

    embeddings = JinaEmbeddings(
        api_key=app_config.jina_api_key,
        url=app_config.jina_embed_url,
        model=app_config.jina_embed_model,
    )

    reranker = JinaRerankCompressor(
        api_key=app_config.jina_api_key,
        url=app_config.jina_rerank_url,
        model=app_config.jina_rerank_model,
        top_n=app_config.reranker_top_n,
    )

    qdrant_client = QdrantClient(
        url=app_config.qdrant_url,
        api_key=app_config.qdrant_api_key,
    )

    model_name = app_config.openai_model if app_config.llm_provider == "openai" else app_config.bedrock_model_id
    llm = get_llm(
        provider=app_config.llm_provider,
        model=model_name,
        temperature=app_config.llm_temperature,
        max_tokens=app_config.llm_max_tokens,
    )

    aws_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    aws_profile = os.environ.get("AWS_PROFILE")
    import boto3

    boto_session = boto3.Session(profile_name=aws_profile, region_name=aws_region) if aws_profile else None

    if checkpointer is None:
        checkpointer = DynamoDBSaver(
            table_name=app_config.dynamodb_checkpoint_table,
            region_name=aws_region,
            session=boto_session,
        )

    if store is None:
        store = DynamoDBStore(
            table_name=app_config.dynamodb_store_table,
            region_name=aws_region,
            boto3_session=boto_session,
        )

    if search_tool is None:
        search_tool = create_search_tweets_tool(
            qdrant_client=qdrant_client,
            collection_name=app_config.collection_name,
            embeddings=embeddings,
            compressor=reranker,
            limit=app_config.retriever_k,
        )

    graph = build_agent_workflow(
        search_tool=search_tool,
        checkpointer=checkpointer,
        store=store,
    )

    services = {
        "llm": llm,
        "search_tool": search_tool,
        "memory_token_limit": app_config.memory_token_limit,
        "memory_keep_messages": app_config.memory_keep_messages,
    }

    return AgentApp(graph=graph, services=services)
