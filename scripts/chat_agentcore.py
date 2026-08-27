#!/usr/bin/env python3
"""Script CLI interactivo para consultar Bedrock AgentCore Runtime con autenticacion Cognito y streaming SSE."""

import json
import os
import subprocess
import urllib.parse
import uuid
from pathlib import Path

import boto3
import requests

REGION = os.getenv("AWS_REGION", "us-east-1")


def get_terraform_outputs() -> dict[str, str]:
    """Obtiene outputs de Terraform para descubrir ARNs e IDs dinamicamente."""
    tf_dir = Path(__file__).resolve().parent.parent / "terraform" / "main"
    try:
        res = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=tf_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            return {k: v.get("value") for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def load_config() -> dict[str, str]:
    """Carga configuracion desde env vars o Terraform outputs."""
    tf_outs = get_terraform_outputs()
    client_id = os.getenv("COGNITO_CLIENT_ID") or tf_outs.get("cognito_client_id", "tkiaaldrn5ktkclqof7s3gdq2")
    runtime_arn = os.getenv("AGENTCORE_RUNTIME_ARN") or tf_outs.get(
        "agentcore_runtime_arn",
        "arn:aws:bedrock-agentcore:us-east-1:563147762970:runtime/fintwit_rag_dev_agent-4a06Jl5mHc",
    )
    email = os.getenv("COGNITO_DEMO_EMAIL") or tf_outs.get("cognito_demo_email", "demo@fintwit.com")
    password = os.getenv("COGNITO_DEMO_PASSWORD", "FinTwit2026!")
    return {
        "client_id": client_id,
        "runtime_arn": runtime_arn,
        "email": email,
        "password": password,
    }


def get_jwt_token(cfg: dict[str, str]) -> str:
    print("[AUTH] Autenticando contra Amazon Cognito...", end="", flush=True)
    session = boto3.Session(profile_name="dev-admin", region_name=REGION)
    cognito = session.client("cognito-idp")
    resp = cognito.initiate_auth(
        ClientId=cfg["client_id"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": cfg["email"],
            "PASSWORD": cfg["password"],
        },
    )
    token = resp["AuthenticationResult"]["AccessToken"]
    print(" [OK]")
    return token


def main():
    cfg = load_config()
    token = get_jwt_token(cfg)
    session_id = str(uuid.uuid4())
    encoded_arn = urllib.parse.quote(cfg["runtime_arn"], safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    print("\n[READY] FinTwit AgentCore CLI listo. Escribi tu pregunta financiera (o 'salir' para terminar):")
    print("-" * 70)

    while True:
        try:
            prompt = input("\nVos: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not prompt or prompt.lower() in ("salir", "exit", "quit"):
            print("\nHasta luego!")
            break

        payload = {
            "threadId": session_id,
            "runId": str(uuid.uuid4()),
            "state": {},
            "messages": [{"role": "user", "content": prompt, "id": str(uuid.uuid4())}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }

        print("\nFinTwit: ", end="", flush=True)
        try:
            resp = requests.post(url, headers=headers, json=payload, stream=True)
            if resp.status_code == 429:
                err = resp.json()
                print(f"\n[RATE_LIMIT] Limite alcanzado: {err.get('detail', 'Reintenta mas tarde.')}")
                continue
            if resp.status_code != 200:
                print(f"\n[ERROR] HTTP {resp.status_code}: {resp.text}")
                continue

            # Parsear eventos SSE de AG-UI
            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("data:"):
                    raw_data = decoded[5:].strip()
                    try:
                        event = json.loads(raw_data)
                        ev_type = event.get("type")

                        if ev_type == "TEXT_MESSAGE_CONTENT":
                            raw = event.get("rawEvent", {})
                            node = raw.get("metadata", {}).get("langgraph_node", "")
                            if node == "check_relevance":
                                continue
                            delta = (
                                event.get("delta")
                                or event.get("content")
                                or event.get("text")
                                or raw.get("data", {}).get("chunk", {}).get("content", "")
                            )
                            if delta:
                                print(delta, end="", flush=True)
                        elif ev_type == "STEP_STARTED":
                            step_name = event.get("stepName")
                            if step_name in ("agent_node", "tools", "check_relevance", "synthesize", "rewrite_query"):
                                print(f" [{step_name}]", end="", flush=True)
                        elif ev_type == "RUN_ERROR":
                            print(f"\n[AGENT_ERROR] {event.get('message')}")
                        elif ev_type == "MESSAGES_SNAPSHOT":
                            pass
                    except json.JSONDecodeError:
                        pass
            print()

        except Exception as exc:
            print(f"\n[ERROR] Red: {exc}")


if __name__ == "__main__":
    main()
