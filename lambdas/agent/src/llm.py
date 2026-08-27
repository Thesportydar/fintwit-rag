import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel


def get_llm(
    provider: str = "openai",
    temperature: float | None = 0.3,
    max_tokens: int = 1024,
) -> BaseChatModel:
    if provider == "openai":
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        # Modelos reasoning (gpt-5.x, o1, o3) solo admiten default temperature (None) y reasoning_effort="none" para tools
        is_reasoning_model = any(prefix in model_name for prefix in ["gpt-5", "o1", "o3"])

        kwargs = {"model": model_name, "model_provider": "openai"}
        if not is_reasoning_model and temperature is not None:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = None
            kwargs["reasoning_effort"] = "none"

        return init_chat_model(**kwargs)

    if provider == "bedrock":
        return init_chat_model(
            os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0"),
            model_provider="bedrock_converse",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(f"LLM provider desconocido: '{provider}'. Opciones: openai | bedrock")
