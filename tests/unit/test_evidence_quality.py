from datetime import date

from agent.src.evidence_quality import format_evidence_quality, grade_evidence, parse_formatted_evidence


def test_parse_formatted_evidence_extracts_safe_metadata():
    documents = parse_formatted_evidence(
        '<tweet id="tweet:1" author="@analista" date="2026-01-02" sentiment="bullish">GGAL &amp; bancos</tweet>'
    )

    assert documents[0]["evidence_id"] == "tweet:1"
    assert documents[0]["content"] == "GGAL & bancos"


def test_grade_evidence_flags_contradiction_and_staleness():
    quality = grade_evidence(
        [
            {"author": "@a", "date": "2025-01-01", "sentiment": "bullish"},
            {"author": "@b", "date": "2025-01-02", "sentiment": "bearish"},
        ],
        as_of=date(2026, 1, 1),
        freshness_days=180,
    )

    assert quality.contradiction_detected is True
    assert quality.stale is True
    assert quality.coverage == "partial"
    assert len(quality.limitations) == 2


def test_format_evidence_quality_is_prompt_readable():
    rendered = format_evidence_quality(
        {
            "document_count": 3,
            "unique_authors": 2,
            "coverage": "partial",
            "contradiction_detected": True,
            "stale": False,
            "freshest_date": "2026-01-02",
            "limitations": ["La evidencia contiene posturas alcistas y bajistas."],
        }
    )

    assert "Documentos recuperados: 3" in rendered
    assert "Posturas contradictorias detectadas: si" in rendered
    assert "- La evidencia contiene posturas alcistas y bajistas." in rendered
    assert "'document_count':" not in rendered
