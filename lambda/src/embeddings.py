from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        raise NotImplementedError


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[int]:
        raise NotImplementedError


@dataclass(frozen=True)
class JinaEmbeddingConfig:
    api_key: str
    embed_url: str
    rerank_url: str
    embed_model: str
    rerank_model: str
    embed_timeout: int = 10
    rerank_timeout: int = 15


class JinaEmbeddingProvider(EmbeddingProvider, Reranker):
    def __init__(self, config: JinaEmbeddingConfig):
        self.config = config

    def embed_query(self, query: str) -> list[float]:
        response = requests.post(
            self.config.embed_url,
            headers=self._headers(),
            json={
                "model": self.config.embed_model,
                "task": "retrieval.query",
                "truncate": True,
                "normalized": True,
                "input": [query],
            },
            timeout=self.config.embed_timeout,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[int]:
        response = requests.post(
            self.config.rerank_url,
            headers=self._headers(),
            json={
                "model": self.config.rerank_model,
                "query": query,
                "top_n": top_n,
                "documents": documents,
                "return_documents": False,
                "truncation": True,
                "max_doc_length": 1024,
            },
            timeout=self.config.rerank_timeout,
        )
        response.raise_for_status()
        return [result["index"] for result in response.json()["results"]]

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
