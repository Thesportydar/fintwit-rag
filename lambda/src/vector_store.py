import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor
from langchain_core.embeddings import Embeddings
from langchain_core.tools import tool
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue


@dataclass(frozen=True)
class TweetFilters:
    start_date: str | None = None
    end_date: str | None = None
    user_handles: list[str] = field(default_factory=list)

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
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                user_handles=list(handles),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("filters tiene valores inválidos") from exc

    def to_qdrant_filter(self) -> Filter | None:
        conditions = []
        if self.user_handles:
            if len(self.user_handles) > 1:
                conditions.append(FieldCondition(key="metadata.user_handle", match=MatchAny(any=self.user_handles)))
            else:
                conditions.append(
                    FieldCondition(key="metadata.user_handle", match=MatchValue(value=self.user_handles[0]))
                )

        if self.start_date or self.end_date:
            from qdrant_client.models import Range

            gte = int(self.start_date[:4]) if self.start_date and len(self.start_date) >= 4 else None
            lte = int(self.end_date[:4]) if self.end_date and len(self.end_date) >= 4 else None
            conditions.append(FieldCondition(key="metadata.tweet_year", range=Range(gte=gte, lte=lte)))

        return Filter(must=conditions) if conditions else None


def _format_doc(d: Document) -> str:
    meta = d.metadata or {}
    handle = meta.get("user_handle", "unknown")
    timestamp = meta.get("tweet_timestamp", "")
    date = timestamp[:10] if timestamp else "unknown"

    parts = [
        "<<< TWEET >>>",
        f"autor: @{handle}",
        f"fecha: {date}",
        f"contenido: {d.page_content}",
        "<<< /TWEET >>>",
    ]
    return "\n".join(parts)


def create_search_tweets_tool(
    qdrant_client: QdrantClient,
    collection_name: str,
    embeddings: Embeddings,
    compressor: BaseDocumentCompressor,
    k: int = 50,
):
    """
    Construye la herramienta @tool de búsqueda que inyecta los filtros en el
    QdrantVectorStore y utiliza el compressor para re-rankear los resultados.
    """
    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        embedding=embeddings,
        content_payload_key="content",  # el payload usa 'content', no 'page_content'
    )

    @tool(response_format="content_and_artifact")
    def search_tweets(
        query: str,
        start_date: str = None,
        end_date: str = None,
        user_handles: list[str] = None,
    ) -> tuple[str, list[Document]]:
        """
        Busca tweets financieros en la base de datos de fintwit.

        La búsqueda es semántica: entiende significado, no palabras clave.
        Formulá la query como una frase o pregunta en lenguaje natural que
        describa la idea que buscás. Evitá listas de palabras sueltas o
        combinaciones con OR/AND.

        BIEN: "visión de la comunidad sobre Bitcoin como cobertura al dólar"
        BIEN: "preocupación por suba de tasas de la Fed en mercados emergentes"
        MAL:  "Bitcoin BTC outlook reserva valor cripto"
        MAL:  "inflación OR Fed OR CPI OR tasas"

        Args:
            query: Frase en lenguaje natural que describa el contenido buscado.
            start_date: Fecha de inicio en formato YYYY-MM-DD. Opcional.
            end_date: Fecha de fin en formato YYYY-MM-DD. Opcional.
            user_handles: Lista de usuarios a filtrar. Usar SOLO si el usuario mencionó una cuenta específica por su @handle exacto.
        """
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        if start_date and not date_pattern.match(start_date):
            return f"Error de validación: start_date '{start_date}' no tiene el formato correcto YYYY-MM-DD.", []
        if end_date and not date_pattern.match(end_date):
            return f"Error de validación: end_date '{end_date}' no tiene el formato correcto YYYY-MM-DD.", []

        # Normalizar handles: quitar @ si viene con él (el payload no los tiene)
        clean_handles = [h.lstrip("@") for h in (user_handles or [])]

        filters = TweetFilters(
            start_date=start_date,
            end_date=end_date,
            user_handles=clean_handles,
        )
        qdrant_filter = filters.to_qdrant_filter()

        # Al usar post-filtrado por fechas exactas, pedimos un k mayor a Qdrant
        search_kwargs = {"k": k}
        if qdrant_filter is not None:
            search_kwargs["filter"] = qdrant_filter

        docs = vectorstore.similarity_search(query, **search_kwargs)

        if start_date or end_date:
            filtered_docs = []
            for doc in docs:
                ts = doc.metadata.get("tweet_timestamp", "")[:10]
                if not ts:
                    continue
                if start_date and ts < start_date:
                    continue
                if end_date and ts > end_date:
                    continue
                filtered_docs.append(doc)
            docs = filtered_docs

        if not docs:
            return "No se encontraron resultados para los filtros especificados.", []

        reranked_docs = compressor.compress_documents(docs, query)

        if not reranked_docs:
            return "No se encontraron resultados relevantes tras el re-ranking.", []

        serialized = "\n\n".join([_format_doc(d) for d in reranked_docs])
        return serialized, reranked_docs

    return search_tweets
