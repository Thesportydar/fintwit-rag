import json

from src import handler as handler_module
from src.handler import SearchRequest, format_context, lambda_handler
from src.vector_store import SearchResult, TweetFilters, TweetHit


class FakeEmbeddingProvider:
    def __init__(self):
        self.embed_calls = []
        self.rerank_calls = []

    def embed_query(self, query: str) -> list[float]:
        self.embed_calls.append(query)
        return [0.1, 0.2, 0.3]

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[int]:
        self.rerank_calls.append((query, documents, top_n))
        return list(range(min(top_n, len(documents))))


class FakeVectorStore:
    def __init__(self, points: list[TweetHit]):
        self.points = points
        self.calls = []

    def query(self, query_vector: list[float], limit: int, filters: TweetFilters | None = None) -> SearchResult:
        self.calls.append((query_vector, limit, filters))
        return SearchResult(points=self.points)


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return "respuesta sintetica"


def test_format_context_uses_explicit_block_delimiters():
    context = format_context(
        [
            TweetHit(
                payload={
                    "tweet_timestamp": "2026-06-06T10:00:00Z",
                    "user_handle": "uno",
                    "content": "primer tweet",
                }
            )
        ]
    )

    assert "<<< TWEET >>>" in context
    assert "<<< /TWEET >>>" in context
    assert "fecha: 2026-06-06" in context
    assert "autor: @uno" in context
    assert "contenido: primer tweet" in context


def test_search_request_from_body_parses_filters_and_limits():
    request = SearchRequest.from_body(
        {
            "query": "bitcoin",
            "retrieve_limit": "12",
            "top_n": 3,
            "filters": {"year": "2024", "user_handles": "merval", "is_retweet": "false"},
        }
    )

    assert request.query == "bitcoin"
    assert request.retrieve_limit == 12
    assert request.top_n == 3
    assert request.filters.year == 2024
    assert request.filters.user_handles == ["merval"]
    assert request.filters.is_retweet is False


def test_lambda_handler_returns_api_gateway_response(monkeypatch):
    points = [
        TweetHit(
            payload={
                "tweet_timestamp": "2026-06-06T12:30:00Z",
                "user_handle": "abc",
                "content": "tweet uno",
                "url": "https://x.com/abc/status/1",
            }
        ),
        TweetHit(
            payload={
                "tweet_timestamp": "2026-06-06T13:30:00Z",
                "user_handle": "def",
                "content": "tweet dos",
                "url": "https://x.com/def/status/2",
            }
        ),
    ]
    fake_embeddings = FakeEmbeddingProvider()
    fake_store = FakeVectorStore(points)
    fake_llm = FakeLLM()

    monkeypatch.setattr(handler_module, "embedding_provider", fake_embeddings)
    monkeypatch.setattr(handler_module, "vector_store", fake_store)
    monkeypatch.setattr(handler_module, "llm", fake_llm)

    response = lambda_handler(
        {
            "body": json.dumps(
                {
                    "query": "consulta",
                    "retrieve_limit": 2,
                    "top_n": 1,
                    "filters": {"year": 2026},
                }
            )
        },
        None,
    )

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    payload = json.loads(response["body"])
    assert payload["answer"] == "respuesta sintetica"
    assert payload["sources"] == [
        {
            "url": "https://x.com/abc/status/1",
            "handle": "abc",
            "date": "2026-06-06",
            "content": "tweet uno",
        }
    ]
    assert fake_embeddings.embed_calls == ["consulta"]
    assert fake_embeddings.rerank_calls[0][0] == "consulta"
    assert fake_store.calls[0][1] == 2
    assert fake_llm.calls[0][0] == handler_module.SYSTEM_PROMPT


def test_lambda_handler_returns_400_for_invalid_input():
    response = lambda_handler({"body": json.dumps({"top_n": 0})}, None)

    assert response["statusCode"] == 400
    payload = json.loads(response["body"])
    assert payload["error"] == "El campo 'query' es requerido"
