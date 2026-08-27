from __future__ import annotations

import json
import logging

from .agent import create_agent_app

logger = logging.getLogger()
logger.setLevel(logging.INFO)

agent_app = create_agent_app()


def lambda_handler(event: dict, context: object) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")

        messages = body.get("messages")
        if not messages and "query" in body:
            messages = [{"role": "user", "content": body["query"]}]
        if not messages:
            return _response(400, {"error": "El campo 'messages' o 'query' es requerido en el body."})

        thread_id = body.get("thread_id", "default_thread")
        extra_configurable = body.get("extra_configurable")

        result = agent_app.invoke(
            messages=messages,
            thread_id=thread_id,
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

        last_content = response_messages[-1]["content"] if response_messages else ""
        return _response(
            200,
            {
                "messages": response_messages,
                "response": last_content,
            },
        )

    except Exception as exc:
        logger.error("Unhandled error in lambda_handler", exc_info=True)
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
