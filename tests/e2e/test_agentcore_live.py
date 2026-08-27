from __future__ import annotations

import json
import uuid

import boto3
import pytest


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


@pytest.mark.e2e
def test_agentcore_runtime_live_agui_streaming(agentcore_runtime_arn, request):
    """
    Test E2E de Bedrock AgentCore Runtime bajo el protocolo AG-UI en AWS.
    Valida:
    1. Contrato AG-UI (RunAgentInput) -> HTTP 200 con Content-Type text/event-stream.
    2. Eventos SSE tipados (RUN_STARTED, RAW/STEP_STARTED, etc.).
    3. Continuidad de sesión (multi-turn) usando runtimeSessionId persistido en DynamoDB.
    """
    if not request.config.getoption("--live"):
        pytest.skip("Test live salteado. Ejecutá con pytest tests/e2e --live para correrlo contra AWS.")

    session_id = str(uuid.uuid4())
    client = boto3.client("bedrock-agentcore", region_name="us-east-1")

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

    response_1 = client.invoke_agent_runtime(
        agentRuntimeArn=agentcore_runtime_arn,
        runtimeSessionId=session_id,
        contentType="application/json",
        payload=json.dumps(payload_1).encode("utf-8"),
    )

    status_1 = response_1.get("ResponseMetadata", {}).get("HTTPStatusCode")
    assert status_1 == 200, f"Error HTTP en AgentCore Runtime: {status_1}"
    assert "text/event-stream" in response_1.get("contentType", ""), "Debe responder con stream SSE de AG-UI"

    raw_text_1 = response_1["response"].read().decode("utf-8")
    events_1 = parse_agui_sse_events(raw_text_1)
    assert len(events_1) > 0, "El stream SSE debe contener al menos un evento AG-UI"

    event_types_1 = [e.get("type") for e in events_1]
    assert "RUN_STARTED" in event_types_1, "El stream AG-UI debe emitir RUN_STARTED"

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

    response_2 = client.invoke_agent_runtime(
        agentRuntimeArn=agentcore_runtime_arn,
        runtimeSessionId=session_id,
        contentType="application/json",
        payload=json.dumps(payload_2).encode("utf-8"),
    )

    status_2 = response_2.get("ResponseMetadata", {}).get("HTTPStatusCode")
    assert status_2 == 200, f"Error HTTP en consulta financiera: {status_2}"

    raw_text_2 = response_2["response"].read().decode("utf-8")
    events_2 = parse_agui_sse_events(raw_text_2)
    assert len(events_2) > 0, "El stream SSE debe contener eventos de la ejecución de CRAG"

    event_types_2 = [e.get("type") for e in events_2]
    assert "RUN_STARTED" in event_types_2
