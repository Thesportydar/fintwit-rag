from __future__ import annotations

import pytest
import requests


@pytest.mark.e2e
def test_live_query_endpoint(api_endpoint, request):
    """
    Test E2E minimalista y agnóstico al backend.
    Solo valida el contrato HTTP público: POST {"query": "...", "thread_id": "..."} -> 200 OK con texto.
    """
    if not request.config.getoption("--live"):
        pytest.skip("Test live salteado. Ejecutá con pytest tests/e2e --live para correrlo contra AWS.")

    payload = {
        "query": "Que comentan en FinTwit sobre Grupo Financiero Galicia ($GGAL) o bancos?",
        "thread_id": "e2e-live-smoke-test",
    }

    response = requests.post(api_endpoint, json=payload, timeout=30)
    assert response.status_code == 200, f"Error HTTP {response.status_code}: {response.text}"

    data = response.json()
    assert "response" in data or "messages" in data, "La respuesta debe contener el texto del agente"

    text = data.get("response") or data.get("messages", [{}])[-1].get("content", "")
    assert len(text.strip()) > 15, "La respuesta del agente no debe estar vacía"
