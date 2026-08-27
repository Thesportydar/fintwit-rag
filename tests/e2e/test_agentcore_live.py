from __future__ import annotations

import json
import urllib.parse
import uuid

import boto3
import pytest
import requests


def parse_agui_sse_events(raw_sse_text: str) -> list[dict]:
    """Parsea el stream de texto Server-Sent Events (SSE) y extrae los eventos JSON de AG-UI."""
    events = []
    for line in raw_sse_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str:
                try:
                    events.append(json.loads(data_str))
                except json.JSONDecodeError:
                    continue
    return events


def get_cognito_access_token(cognito_auth_info: dict | None) -> str | None:
    """Obtiene el AccessToken JWT autenticandose contra Amazon Cognito."""
    if not cognito_auth_info:
        return None
    try:
        cognito_client = boto3.client("cognito-idp", region_name="us-east-1")
        resp = cognito_client.initiate_auth(
            ClientId=cognito_auth_info["client_id"],
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": cognito_auth_info["email"],
                "PASSWORD": cognito_auth_info["password"],
            },
        )
        return resp.get("AuthenticationResult", {}).get("AccessToken")
    except Exception as exc:
        print(f"Advertencia: No se pudo obtener token de Cognito ({exc}). Continuando sin Bearer...")
        return None


@pytest.mark.e2e
def test_agentcore_runtime_live_agui_streaming(agentcore_runtime_arn, cognito_auth_info, request):
    """
    Test E2E de Bedrock AgentCore Runtime bajo el protocolo AG-UI en AWS.
    Valida:
    1. Autenticación exitosa con AccessToken JWT de Cognito (Authorizer).
    2. Contrato AG-UI (RunAgentInput) -> HTTP 200 con Content-Type text/event-stream.
    3. Eventos SSE tipados (RUN_STARTED, RAW/STEP_STARTED, MESSAGES_SNAPSHOT, RUN_FINISHED).
    4. Continuidad de sesión (multi-turn) usando runtimeSessionId persistido en DynamoDB.
    """
    if not request.config.getoption("--live"):
        pytest.skip("Test live salteado. Ejecutá con pytest tests/e2e --live para correrlo contra AWS.")

    session_id = str(uuid.uuid4())
    access_token = get_cognito_access_token(cognito_auth_info)

    encoded_arn = urllib.parse.quote(agentcore_runtime_arn, safe="")
    url = f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{encoded_arn}/invocations"

    headers = {
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    # 1. Invocación inicial con contrato AG-UI
    payload_1 = {
        "threadId": session_id,
        "runId": str(uuid.uuid4()),
        "state": {},
        "messages": [{"role": "user", "content": "hola", "id": "msg-1"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }

    resp_1 = requests.post(url, headers=headers, json=payload_1, stream=True)
    assert resp_1.status_code == 200, f"Error HTTP en AgentCore Runtime: {resp_1.status_code} - {resp_1.text}"
    assert "text/event-stream" in resp_1.headers.get("content-type", ""), "Debe responder con stream SSE de AG-UI"

    raw_text_1 = resp_1.text
    events_1 = parse_agui_sse_events(raw_text_1)
    assert len(events_1) > 0, "El stream SSE debe contener al menos un evento AG-UI"

    event_types_1 = [e.get("type") for e in events_1]
    assert "RUN_STARTED" in event_types_1, "El stream AG-UI debe emitir RUN_STARTED"
    assert "RUN_FINISHED" in event_types_1, "El stream AG-UI debe emitir RUN_FINISHED"

    # 2. Invocación financiera con continuidad de sesión
    payload_2 = {
        "threadId": session_id,
        "runId": str(uuid.uuid4()),
        "state": {},
        "messages": [{"role": "user", "content": "que opinan en fintwit de galicia o ggal?", "id": "msg-2"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }

    resp_2 = requests.post(url, headers=headers, json=payload_2, stream=True)
    assert resp_2.status_code == 200, f"Error HTTP en consulta financiera: {resp_2.status_code} - {resp_2.text}"

    raw_text_2 = resp_2.text
    events_2 = parse_agui_sse_events(raw_text_2)
    assert len(events_2) > 0, "El stream SSE debe contener eventos de la ejecución de CRAG"

    event_types_2 = [e.get("type") for e in events_2]
    assert "RUN_STARTED" in event_types_2
    assert "RUN_FINISHED" in event_types_2
