import os
from abc import ABC, abstractmethod


class BaseLLM(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        ...


class OpenAILLM(BaseLLM):
    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI

        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

    def complete(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message.content


class BedrockLLM(BaseLLM):
    def __init__(self, model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0"):
        import json
        import boto3

        self.client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        self.model_id = model_id
        self._json = json

    def complete(self, system: str, user: str) -> str:
        body = self._json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        )
        response = self.client.invoke_model(modelId=self.model_id, body=body)
        result = self._json.loads(response["body"].read())
        return result["content"][0]["text"]


def get_llm(provider: str = "openai") -> BaseLLM:
    if provider == "openai":
        return OpenAILLM(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))

    if provider == "bedrock":
        return BedrockLLM(model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0"))

    raise ValueError(f"LLM provider desconocido: '{provider}'. Opciones: openai | bedrock")
