import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel


def get_llm(
    provider: str = "openai",
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> BaseChatModel:
    if provider == "openai":
        return init_chat_model(
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            model_provider="openai",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    if provider == "bedrock":
        return init_chat_model(
            os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0"),
            model_provider="bedrock_converse",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(f"LLM provider desconocido: '{provider}'. Opciones: openai | bedrock")
