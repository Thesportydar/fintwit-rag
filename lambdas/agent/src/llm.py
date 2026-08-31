from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel


def get_llm(
    provider: str = "openai",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> BaseChatModel:
    """Instancia el modelo de chat con los hiperparámetros y flags requeridos por el proveedor."""
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model_name = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        is_reasoning_model = any(prefix in model_name for prefix in ("gpt-5", "o1", "o3"))

        kwargs: dict = {
            "model": model_name,
            "max_tokens": max_tokens,
        }
        if is_reasoning_model:
            kwargs["reasoning_effort"] = "none"
        else:
            kwargs["temperature"] = temperature

        return ChatOpenAI(**kwargs)

    if provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        model_name = model or os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
        return ChatBedrockConverse(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(f"LLM provider desconocido: '{provider}'. Opciones: openai | bedrock")
