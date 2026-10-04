"""compare_pdfs() mode dispatch, without needing real PDFs (extractors are stubbed)."""
import pytest

import compare.service as service
from compare.schemas import (
    ClientExecutionStep,
    ClientScript,
    ComparisonMode,
    SetupStep,
)
from tests.helpers import es, pts, script


def _client():
    return ClientScript(
        setup_steps=[SetupStep(1, "Enable feature X")],
        execution_steps=[ClientExecutionStep(1, "Log in", "Home page is displayed")],
        metadata={"script_id": "TS-1", "title": "T", "description": "D"},
    )


def _executed(actual="Home page is displayed"):
    return script(
        [es(1, "Log in", "Home page is displayed", actual)],
        [pts(1, "Enable feature X")],
        script_id="TS-1", title="T", description="D",
    )


def test_default_mode_is_template_vs_output_and_keeps_original_shape(monkeypatch):
    monkeypatch.setattr(service, "extract_client_pdf", lambda p: _client())
    monkeypatch.setattr(service, "extract_executed_pdf", lambda p: _executed())

    r = service.compare_pdfs("a.pdf", "b.pdf")  # original two-argument call

    assert r["comparison_mode"] == "template_vs_output"
    for key in ("has_differences", "summary", "setup_differences", "execution_differences",
                "client_metadata", "executed_metadata", "statistics",
                "executed_steps", "pts_steps"):
        assert key in r
    assert r["has_differences"] is False


def test_output_vs_output_never_touches_the_client_extractor(monkeypatch):
    def boom(_):
        raise AssertionError("client/template extractor must not run in output_vs_output")

    calls = []
    monkeypatch.setattr(service, "extract_client_pdf", boom)
    monkeypatch.setattr(service, "extract_executed_pdf",
                        lambda p: (calls.append(p), _executed("Something else"))[1])

    r = service.compare_pdfs("a.pdf", "b.pdf", ComparisonMode.OUTPUT_VS_OUTPUT)

    assert calls == ["a.pdf", "b.pdf"]  # both PDFs parsed as executed reports
    assert r["comparison_mode"] == "output_vs_output"
    for key in ("summary", "differences", "output_a_metadata", "output_b_metadata",
                "statistics", "output_a_steps", "output_b_steps",
                "output_a_pts_steps", "output_b_pts_steps"):
        assert key in r
    # Template-vs-Output keys must not leak into the peer result
    for key in ("client_metadata", "executed_metadata", "setup_differences",
                "execution_differences", "executed_steps", "pts_steps"):
        assert key not in r


def test_mode_accepts_plain_string_and_rejects_unknown(monkeypatch):
    monkeypatch.setattr(service, "extract_executed_pdf", lambda p: _executed())
    assert service.compare_pdfs("a", "b", "output_vs_output")["comparison_mode"] == "output_vs_output"
    with pytest.raises(ValueError):
        service.compare_pdfs("a", "b", "template_vs_template")
