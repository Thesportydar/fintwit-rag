from __future__ import annotations

import logging
import os
from pathlib import Path

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from dotenv import load_dotenv
from fastapi import FastAPI

# Cargar .env si existe en el filesystem local (en AWS las variables vienen inyectadas en el entorno)
_repo_root = Path(__file__).resolve().parents[3]
_env_path = _repo_root / ".env"
if _env_path.is_file():
    load_dotenv(_env_path, override=False)

try:
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument()
except ImportError:
    pass

from .agent import create_agent_app

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Inicializar grafo de LangGraph
agent_app = create_agent_app()

# Inicializar servidor FastAPI para el protocolo AG-UI
app = FastAPI(
    title="FinTwit AG-UI Agent Runtime",
    description="Agent User Interaction (AG-UI) Server for Amazon Bedrock AgentCore Runtime",
    version="1.0.0",
)


@app.get("/ping")
@app.get("/health")
async def ping() -> dict[str, str]:
    """Health check endpoint requerido por el contrato de Bedrock AgentCore Runtime."""
    return {"status": "Healthy"}


# Montar endpoint AG-UI estándar sobre LangGraph (/invocations)
default_config = agent_app.get_config(thread_id="default")
langgraph_agent = LangGraphAgent(
    name="fintwit_agent",
    graph=agent_app.graph,
    config=default_config,
)
add_langgraph_fastapi_endpoint(app, langgraph_agent, "/invocations")


# Handler síncrono para compatibilidad interna y tests
def agent_invocation(payload: dict, context: object = None) -> dict:
    """Handler síncrono que delega directamente al grafo de LangGraph."""
    prompt = payload.get("prompt")
    messages = payload.get("messages")

    if not messages and prompt:
        messages = [{"role": "user", "content": prompt}]
    elif not messages:
        return {"error": "Invalid input: 'prompt' or 'messages' is required."}

    session_id = (
        getattr(context, "session_id", None)
        or getattr(context, "runtime_session_id", None)
        or payload.get("session_id")
        or payload.get("runtimeSessionId")
        or payload.get("threadId")
        or "default_session"
    )

    extra_configurable = payload.get("extra_configurable")
    result = agent_app.invoke(
        messages=messages,
        thread_id=session_id,
        extra_configurable=extra_configurable,
    )

    response_messages = []
    for m in result.get("messages", []):
        msg_dict = {
            "role": getattr(m, "type", "unknown"),
            "content": getattr(m, "content", ""),
        }
        if hasattr(m, "tool_calls") and m.tool_calls:
            msg_dict["tool_calls"] = m.tool_calls
        response_messages.append(msg_dict)

    last_content = result.get("response") or (response_messages[-1]["content"] if response_messages else "")
    return {
        "result": last_content,
        "response": last_content,
        "messages": response_messages,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
