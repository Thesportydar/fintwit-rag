import json
import logging
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, SummarizationMiddleware, ToolRetryMiddleware
from langgraph_checkpoint_aws import DynamoDBSaver
from langgraph_checkpoint_aws.store.dynamodb import DynamoDBStore
from qdrant_client import QdrantClient

from .config import AppConfig
from .embeddings import JinaEmbeddings, JinaRerankCompressor
from .llm import get_llm
from .vector_store import create_search_tweets_tool

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PROMPTS_DIR = Path(__file__).parent / "prompts"
with open(PROMPTS_DIR / "system_prompt.txt", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read().strip()

app_config = AppConfig.from_env()

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

search_tweets_tool = create_search_tweets_tool(
    qdrant_client=qdrant_client,
    collection_name=app_config.collection_name,
    embeddings=embeddings,
    compressor=reranker,
    k=app_config.retriever_k,
)

llm = get_llm(
    provider=app_config.llm_provider,
    temperature=app_config.llm_temperature,
    max_tokens=app_config.llm_max_tokens,
)

checkpointer = DynamoDBSaver(table_name=app_config.dynamodb_checkpoint_table)

store = DynamoDBStore(table_name=app_config.dynamodb_store_table)

agent = create_agent(
    model=llm,
    tools=[search_tweets_tool],
    checkpointer=checkpointer,
    store=store,
    middleware=[
        ModelRetryMiddleware(
            max_retries=3,
            backoff_factor=2.0,
            initial_delay=1.0,
        ),
        ToolRetryMiddleware(
            max_retries=3,
            backoff_factor=2.0,
            initial_delay=1.0,
        ),
        SummarizationMiddleware(
            model=llm,
            trigger=("tokens", app_config.memory_token_limit),
            keep=("messages", app_config.memory_keep_messages),
        ),
    ],
    system_prompt=SYSTEM_PROMPT,
)


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")

        messages = body.get("messages", [])
        if not messages:
            return _response(400, {"error": "El campo 'messages' es requerido en el body."})

        thread_id = body.get("thread_id", "default_thread")
        config = {"configurable": {"thread_id": thread_id}}

        result = agent.invoke({"messages": messages}, config=config)

        response_messages = []
        for m in result.get("messages", []):
            msg_dict = {
                "role": m.type,
                "content": m.content,
            }
            if hasattr(m, "tool_calls") and m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            response_messages.append(msg_dict)

        return _response(200, {"messages": response_messages})

    except Exception as exc:
        logger.error("Unhandled error", exc_info=True)
        return _response(500, {"error": str(exc)})


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }
