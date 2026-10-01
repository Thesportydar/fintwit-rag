from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from html import unescape
from typing import Any, Literal
from xml.etree import ElementTree

from pydantic import BaseModel, Field

Coverage = Literal["complete", "partial", "insufficient"]


class EvidenceQuality(BaseModel):
    """Deterministic quality signals for the evidence selected for synthesis."""

    document_count: int = Field(ge=0)
    unique_authors: int = Field(ge=0)
    contradiction_detected: bool = False
    stale: bool = False
    freshest_date: str | None = None
    coverage: Coverage
    limitations: list[str] = Field(default_factory=list)


def parse_formatted_evidence(content: str) -> list[dict[str, str]]:
    """Parse the safe XML representation emitted by the search tool."""
    if not content.strip():
        return []

    try:
        root = ElementTree.fromstring(f"<evidence>{content}</evidence>")
    except ElementTree.ParseError:
        return []

    documents = []
    for element in root.findall("tweet"):
        documents.append(
            {
                "evidence_id": element.attrib.get("id", ""),
                "author": element.attrib.get("author", ""),
                "date": element.attrib.get("date", ""),
                "sentiment": element.attrib.get("sentiment", ""),
                "content": unescape("".join(element.itertext())),
            }
        )
    return documents


def grade_evidence(
    documents: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    freshness_days: int = 180,
) -> EvidenceQuality:
    """Grade evidence without an LLM so limitations are explicit and repeatable."""
    if not documents:
        return EvidenceQuality(
            document_count=0,
            unique_authors=0,
            coverage="insufficient",
            limitations=["No se encontraron documentos parseables."],
        )

    authors = {str(document.get("author") or "") for document in documents}
    sentiments = {str(document.get("sentiment") or "") for document in documents}
    contradiction_detected = {"bullish", "bearish"}.issubset(sentiments)
    parsed_dates = []
    for document in documents:
        try:
            parsed_dates.append(date.fromisoformat(str(document.get("date", ""))))
        except ValueError:
            continue

    freshest = max(parsed_dates) if parsed_dates else None
    stale = bool(as_of and freshest and as_of - freshest > timedelta(days=freshness_days))
    limitations = []
    if len(authors - {""}) < 2:
        limitations.append("La evidencia proviene de una sola cuenta o no identifica autor.")
    if contradiction_detected:
        limitations.append("La evidencia contiene posturas alcistas y bajistas.")
    if stale:
        limitations.append(f"La evidencia mas reciente tiene mas de {freshness_days} dias.")
    if not parsed_dates:
        limitations.append("Los documentos no contienen fechas parseables.")

    coverage = "partial" if limitations else "complete"
    return EvidenceQuality(
        document_count=len(documents),
        unique_authors=len(authors - {""}),
        contradiction_detected=contradiction_detected,
        stale=stale,
        freshest_date=freshest.isoformat() if freshest else None,
        coverage=coverage,
        limitations=limitations,
    )


def format_evidence_quality(quality: Mapping[str, Any]) -> str:
    """Render deterministic evidence signals as concise instructions for the LLM."""
    limitations = quality.get("limitations") or []
    limitation_lines = "\n".join(f"- {str(limitation)}" for limitation in limitations)
    if not limitation_lines:
        limitation_lines = "- No se registraron limitaciones deterministas."

    return "\n".join(
        [
            f"Documentos recuperados: {quality.get('document_count', 0)}",
            f"Autores unicos: {quality.get('unique_authors', 0)}",
            f"Cobertura estimada: {quality.get('coverage', 'insufficient')}",
            f"Posturas contradictorias detectadas: {'si' if quality.get('contradiction_detected') else 'no'}",
            f"Contexto desactualizado: {'si' if quality.get('stale') else 'no'}",
            f"Fecha mas reciente: {quality.get('freshest_date') or 'no disponible'}",
            f"Limitaciones:\n{limitation_lines}",
        ]
    )
