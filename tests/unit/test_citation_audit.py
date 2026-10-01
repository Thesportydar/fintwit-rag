from agent.src.citation_audit import audit_citations, extract_evidence_citations


def test_extract_evidence_citations_deduplicates_ids():
    assert extract_evidence_citations("[evidence:a] [evidence:a] [evidence:b]") == ["a", "b"]


def test_audit_citations_reports_invalid_ids_without_rejecting_response():
    evidence = '<tweet id="a" author="@one" date="2024-01-01">A</tweet>'

    audit = audit_citations("[evidence:a] [evidence:missing]", evidence)

    assert audit["status"] == "invalid"
    assert audit["valid_citations"] == ["a"]
    assert audit["invalid_citations"] == ["missing"]


def test_audit_citations_reports_missing_citations():
    evidence = '<tweet id="a" author="@one" date="2024-01-01">A</tweet>'

    audit = audit_citations("No hay citas.", evidence)

    assert audit["status"] == "missing"
    assert audit["cited_evidence_coverage"] == 0.0
