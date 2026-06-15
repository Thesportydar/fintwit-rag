from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import requests
from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor
from langchain_core.embeddings import Embeddings


class JinaEmbeddings(Embeddings):
    """LangChain-compatible Embeddings backed by the Jina AI embeddings API.

    Supports the ``task`` parameter (``retrieval.query`` / ``retrieval.passage``)
    that the community integration is missing.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        url: str,
        timeout: int = 10,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = url
        self._timeout = timeout

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of passage strings (retrieval.passage task)."""
        return self._embed(texts, task="retrieval.passage")

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (retrieval.query task)."""
        return self._embed([text], task="retrieval.query")[0]

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        response = requests.post(
            self._url,
            headers=self._headers(),
            json={
                "model": self._model,
                "task": task,
                "truncate": True,
                "normalized": True,
                "input": texts,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()["data"]
        # API returns objects sorted by index; sort defensively
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }


class JinaRerankCompressor(BaseDocumentCompressor):
    """LangChain-compatible document compressor backed by the Jina AI reranker API.

    Implements ``BaseDocumentCompressor``.
    """

    api_key: str
    model: str
    url: str
    top_n: int = 5
    max_doc_length: int = 1024
    timeout: int = 15

    class Config:
        arbitrary_types_allowed = True

    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Any = None,
    ) -> Sequence[Document]:
        """Rerank *documents* against *query* and return top_n in ranked order."""
        if not documents:
            return []

        texts = [doc.page_content for doc in documents]
        ranked_indices = self._rerank(query=query, documents=texts)

        # Return documents in ranked order, preserving original metadata
        return [documents[i] for i in ranked_indices]

    def _rerank(self, query: str, documents: list[str]) -> list[int]:
        response = requests.post(
            self.url,
            headers=self._headers(),
            json={
                "model": self.model,
                "query": query,
                "top_n": self.top_n,
                "documents": documents,
                "return_documents": False,
                "truncation": True,
                "max_doc_length": self.max_doc_length,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [result["index"] for result in response.json()["results"]]

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
