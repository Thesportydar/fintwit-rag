import asyncio
import base64
import json
import logging
import os
import time
from decimal import Decimal
from pathlib import Path

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

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

# Configurar CORS restrictivo
_allowed_origins = [origin.strip() for origin in app_config.allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
async def safety_and_rate_limit_middleware(request: Request, call_next):
    """Aplica validaciones de seguridad, control de abuso y Rate Limiting global en DynamoDB."""
    if request.url.path in ("/ping", "/health"):
        return await call_next(request)

    # Validaciones de Seguridad de Input y Turnos para llamadas a /invocations
    if request.url.path == "/invocations" and request.method == "POST":
        try:
            body_bytes = await request.body()
            if body_bytes:
                data = json.loads(body_bytes)
                messages = data.get("messages", [])

                # 1. Validar límite de longitud de texto en el input del usuario
                for m in messages:
                    if m.get("role") in ("user", "human"):
                        content = m.get("content", "")
                        if isinstance(content, str) and len(content) > app_config.max_input_chars:
                            logger.warning(
                                "Mensaje de usuario excede limite de %d caracteres (longitud: %d)",
                                app_config.max_input_chars,
                                len(content),
                            )
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "error": "Input length exceeded",
                                    "detail": f"El mensaje supera el límite máximo permitido de {app_config.max_input_chars} caracteres.",
                                },
                            )
                        elif isinstance(content, list):
                            total_chars = sum(len(part.get("text", "")) for part in content if isinstance(part, dict))
                            if total_chars > app_config.max_input_chars:
                                logger.warning(
                                    "Mensaje de usuario excede limite de %d caracteres (longitud: %d)",
                                    app_config.max_input_chars,
                                    total_chars,
                                )
                                return JSONResponse(
                                    status_code=400,
                                    content={
                                        "error": "Input length exceeded",
                                        "detail": f"El mensaje supera el límite máximo permitido de {app_config.max_input_chars} caracteres.",
                                    },
                                )

                # 2. Validar límite de turnos por conversación
                user_msg_count = sum(1 for m in messages if m.get("role") in ("user", "human"))
                if user_msg_count > app_config.max_thread_turns:
                    logger.warning(
                        "Conversacion excede limite de %d turnos (turnos: %d)",
                        app_config.max_thread_turns,
                        user_msg_count,
                    )
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "Thread limit reached",
                            "detail": f"Esta conversación ha alcanzado el límite máximo de {app_config.max_thread_turns} turnos. Por favor iniciá una Nueva Conversación.",
                        },
                    )
        except Exception as err:
            logger.warning("No se pudo parsear el body de invocacion para validacion de seguridad: %s", err)

    auth_header = request.headers.get("authorization", "")
    claims = _extract_jwt_claims(auth_header)

    username = str(claims.get("username") or claims.get("cognito:username") or claims.get("email") or "")
    groups = claims.get("cognito:groups") or []
    if not isinstance(groups, list):
        groups = [groups]

    # Bypass total de rate limit para usuario administrador
    admin_target = app_config.admin_email.lower()
    if (username and username.lower() == admin_target) or any(str(g).lower() == "admin" for g in groups):
        resp = await call_next(request)
        return _wrap_with_timeout(resp)

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

    resp = await call_next(request)
    return _wrap_with_timeout(resp)


def _wrap_with_timeout(resp):
    """Envuelve la respuesta en timeout estricto de ejecucion si es StreamingResponse."""
    if isinstance(resp, StreamingResponse) and app_config.invocation_timeout_seconds > 0:
        orig_body_iterator = resp.body_iterator

        async def timed_iter():
            try:
                async with asyncio.timeout(app_config.invocation_timeout_seconds):
                    async for chunk in orig_body_iterator:
                        yield chunk
            except TimeoutError:
                logger.warning(
                    "Invocación cortada por timeout de %ds.",
                    app_config.invocation_timeout_seconds,
                )
                yield f'data: {{"type": "RUN_ERROR", "code": "TIMEOUT", "message": "La ejecución superó el tiempo límite de {app_config.invocation_timeout_seconds} segundos."}}\n\n'.encode()

        resp.body_iterator = timed_iter()
    return resp


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
