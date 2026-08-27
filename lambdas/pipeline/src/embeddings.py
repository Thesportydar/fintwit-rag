from __future__ import annotations

import requests


class JinaEmbeddingService:
    def __init__(
        self,
        api_key: str,
        url: str = "https://api.jina.ai/v1/embeddings",
        model: str = "jina-embeddings-v5-text-nano",
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.url = url
        self.model = model
        self.timeout = timeout

    def embed_texts(self, texts: list[str], task: str = "retrieval.passage") -> list[list[float]]:
        if not texts:
            return []

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "task": task,
            "truncate": True,
            "normalized": True,
            "input": texts,
        }

        response = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json().get("data", [])
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]
