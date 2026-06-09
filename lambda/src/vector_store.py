from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue


@dataclass(frozen=True)
class TweetFilters:
    year: int | None = None
    month: int | None = None
    session: str | None = None
    user_handles: list[str] = field(default_factory=list)
    is_retweet: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TweetFilters":
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("filters debe ser un objeto JSON")

        handles = data.get("user_handles", [])
        if isinstance(handles, str):
            handles = [handles]
        elif handles is None:
            handles = []
        try:
            return cls(
                year=_to_int(data.get("year")),
                month=_to_int(data.get("month")),
                session=data.get("session"),
                user_handles=list(handles),
                is_retweet=_to_bool(data["is_retweet"]) if "is_retweet" in data and data["is_retweet"] is not None else None,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("filters tiene valores inválidos") from exc

    def to_qdrant_filter(self) -> Filter | None:
        conditions = []
        if self.year is not None:
            conditions.append(FieldCondition(key="tweet_year", match=MatchValue(value=self.year)))
        if self.month is not None:
            conditions.append(FieldCondition(key="tweet_month", match=MatchValue(value=self.month)))
        if self.session is not None:
            conditions.append(FieldCondition(key="session", match=MatchValue(value=self.session)))
        if self.user_handles:
            if len(self.user_handles) > 1:
                conditions.append(FieldCondition(key="user_handle", match=MatchAny(any=self.user_handles)))
            else:
                conditions.append(FieldCondition(key="user_handle", match=MatchValue(value=self.user_handles[0])))
        if self.is_retweet is not None:
            conditions.append(FieldCondition(key="is_retweet", match=MatchValue(value=self.is_retweet)))
        return Filter(must=conditions) if conditions else None


@dataclass(frozen=True)
class TweetHit:
    payload: dict[str, Any]
    score: float | None = None
    point_id: str | int | None = None

    @property
    def content(self) -> str:
        return str(self.payload.get("content", ""))


@dataclass(frozen=True)
class SearchResult:
    points: list[TweetHit]


class TweetVectorStore(ABC):
    @abstractmethod
    def query(self, query_vector: list[float], limit: int, filters: TweetFilters | None = None) -> SearchResult:
        raise NotImplementedError


@dataclass
class QdrantStoreConfig:
    url: str
    api_key: str | None
    collection_name: str


class QdrantTweetVectorStore(TweetVectorStore):
    def __init__(self, config: QdrantStoreConfig):
        self.config = config
        self.client = QdrantClient(url=config.url, api_key=config.api_key)

    def query(self, query_vector: list[float], limit: int, filters: TweetFilters | None = None) -> SearchResult:
        response = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=filters.to_qdrant_filter() if filters else None,
        )
        points = [
            TweetHit(payload=point.payload or {}, score=getattr(point, "score", None), point_id=getattr(point, "id", None))
            for point in (response.points or [])
        ]
        return SearchResult(points=points)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return bool(value)
