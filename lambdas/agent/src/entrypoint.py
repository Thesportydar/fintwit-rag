from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Cargar .env opcionalmente si dotenv esta instalado y existe el archivo local
try:
    from dotenv import load_dotenv

    _repo_root = Path(__file__).resolve().parents[3]
    _env_path = _repo_root / ".env"
    if _env_path.is_file():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass

try:
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument()
except ImportError:
    pass

try:
    from .agent import create_agent_app
    from .config import AppConfig
except (ImportError, ValueError):
    from src.agent import create_agent_app
    from src.config import AppConfig

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Cargar configuracion centralizada
app_config = AppConfig.from_env()

# Inicializar grafo de LangGraph
agent_app = create_agent_app(app_config=app_config)

# Inicializar servidor FastAPI para el protocolo AG-UI
app = FastAPI(
    title="FinTwit AG-UI Agent Runtime",
    description="Agent User Interaction (AG-UI) Server for Amazon Bedrock AgentCore Runtime",
    version="1.0.0",
)

import base64
import json
from decimal import Decimal


class DynamoDBRateLimiter:
    """Rate limiter distribuido respaldado por Amazon DynamoDB con TTL automático."""

    def __init__(self, table_name: str, region_name: str | None = None):
        self.table_name = table_name
        self.region_name = (
            region_name or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        )
        self._dynamodb = None
        self._table = None

    @property
    def table(self):
        if self._table is None:
            import boto3

            aws_profile = os.environ.get("AWS_PROFILE")
            session = (
                boto3.Session(profile_name=aws_profile, region_name=self.region_name)
                if aws_profile
                else boto3.Session(region_name=self.region_name)
            )
            self._dynamodb = session.resource("dynamodb")
            self._table = self._dynamodb.Table(self.table_name)
        return self._table

    def check_and_record(
        self,
        client_key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Verifica y registra una solicitud en DynamoDB usando ventana deslizante con TTL.
        Retorna:
          (allowed: bool, retry_after: int)
        """
        now = time.time()
        cutoff = now - window_seconds
        ttl_time = int(now + window_seconds + 300)

        try:
            resp = self.table.get_item(
                Key={"PK": f"RATE_LIMIT#{client_key}"},
                ConsistentRead=True,
            )
            item = resp.get("Item", {})
            raw_timestamps = item.get("timestamps", [])

            active_timestamps = [Decimal(str(ts)) for ts in raw_timestamps if float(ts) > cutoff]

            if len(active_timestamps) >= max_requests:
                earliest = float(active_timestamps[0])
                retry_after = max(1, int(window_seconds - (now - earliest)))
                return False, retry_after

            active_timestamps.append(Decimal(str(now)))
            self.table.put_item(
                Item={
                    "PK": f"RATE_LIMIT#{client_key}",
                    "timestamps": active_timestamps,
                    "expires_at": ttl_time,
                }
            )
            return True, 0

        except Exception as exc:
            logger.warning(
                "Fallo al consultar DynamoDB rate limiter (%s): %s. Fail-open permitido.",
                self.table_name,
                exc,
            )
            return True, 0


# Instancia central de DynamoDB Rate Limiter
rate_limiter = DynamoDBRateLimiter(table_name=app_config.dynamodb_rate_limit_table)


def _extract_jwt_claims(auth_header: str) -> dict:
    """Extrae claims del payload JWT sin verificar la firma (Bedrock AgentCore Authorizer ya la valido)."""
    if not auth_header.startswith("Bearer "):
        return {}
    token = auth_header[7:].strip()
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        return json.loads(payload_bytes)
    except Exception:
        return {}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Aplica Rate Limiting global en DynamoDB para usuarios demo y permite bypass para admin."""
    if request.url.path in ("/ping", "/health"):
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    claims = _extract_jwt_claims(auth_header)

    username = str(claims.get("username") or claims.get("cognito:username") or claims.get("email") or "")
    groups = claims.get("cognito:groups") or []
    if not isinstance(groups, list):
        groups = [groups]

    # Bypass total de rate limit para usuario administrador
    admin_target = app_config.admin_email.lower()
    if (username and username.lower() == admin_target) or any(str(g).lower() == "admin" for g in groups):
        return await call_next(request)

    # Cuota global compartida en DynamoDB para todos los visitantes demo (previene ataques de rotacion de IP)
    client_key = "global_demo_pool"
    allowed, retry_after = rate_limiter.check_and_record(
        client_key=client_key,
        max_requests=app_config.rate_limit_requests,
        window_seconds=app_config.rate_limit_window_seconds,
    )

    if not allowed:
        logger.warning(
            "Rate limit global demo excedido en DynamoDB: %d solicitudes permitidas cada %d segundos.",
            app_config.rate_limit_requests,
            app_config.rate_limit_window_seconds,
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Limite global de {app_config.rate_limit_requests} consultas cada {app_config.rate_limit_window_seconds // 60} minutos excedido. Por favor intenta mas tarde.",
                "retry_after_seconds": retry_after,
            },
        )

    return await call_next(request)


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
