from __future__ import annotations

import logging
import re
from typing import Any

from .evidence_quality import parse_formatted_evidence

_EVIDENCE_CITATION_PATTERN = re.compile(r"\[evidence:([^\]\s]+)\]")
logger = logging.getLogger(__name__)


def extract_evidence_citations(text: str) -> list[str]:
    """Extract unique evidence IDs cited in a synthesized response."""
    citations = _EVIDENCE_CITATION_PATTERN.findall(text or "")
    return list(dict.fromkeys(citations))


def audit_citations(response: str, evidence_context: str) -> dict[str, Any]:
    """Audit citation references without modifying or rejecting the response."""
    available_ids = {
        document["evidence_id"]
        for document in parse_formatted_evidence(evidence_context)
        if document.get("evidence_id")
    }
    citations = extract_evidence_citations(response)
    valid_citations = [citation for citation in citations if citation in available_ids]
    invalid_citations = [citation for citation in citations if citation not in available_ids]
    cited_evidence_coverage = len(valid_citations) / len(available_ids) if available_ids else 0.0

    if not citations:
        status = "missing" if available_ids else "no_evidence"
    elif invalid_citations:
        status = "invalid"
    elif len(valid_citations) < len(available_ids):
        status = "partial"
    else:
        status = "complete"

    audit = {
        "status": status,
        "available_evidence_count": len(available_ids),
        "cited_evidence_count": len(valid_citations),
        "citation_count": len(citations),
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "cited_evidence_coverage": round(cited_evidence_coverage, 3),
    }
    if status in {"missing", "invalid"}:
        logger.warning("Auditoria de citas de evidencia: %s", audit)
    return audit
