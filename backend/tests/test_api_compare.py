"""POST /compare: backward-compatible fields, new comparison_mode, error handling."""
import os

import pytest
from fastapi.testclient import TestClient

import app as app_module
from auth import UserInfo, get_current_user
from compare.schemas import ComparisonMode

PDF = b"%PDF-1.4\n%fake but has the magic bytes\n"


@pytest.fixture()
def client(monkeypatch):
    seen = {}

    def fake_compare(a_path, b_path, mode):
        with open(a_path, "rb") as fa, open(b_path, "rb") as fb:
            seen.update(a=a_path, b=b_path, mode=mode, a_bytes=fa.read(), b_bytes=fb.read(),
                        a_exists=True, b_exists=True)
        return {"ok": True, "mode": mode.value}

    monkeypatch.setattr(app_module, "compare_pdfs", fake_compare)
    app_module.app.dependency_overrides[get_current_user] = lambda: UserInfo(email="t@t", role="admin")
    c = TestClient(app_module.app)
    c.seen = seen
    yield c
    app_module.app.dependency_overrides.clear()


def _pdf(name="x.pdf", data=PDF):
    return (name, data, "application/pdf")


def test_legacy_fields_without_mode_behave_as_template_vs_output(client):
    r = client.post("/compare", files={"client_pdf": _pdf(), "output_pdf": _pdf()})

    assert r.status_code == 200
    assert client.seen["mode"] is ComparisonMode.TEMPLATE_VS_OUTPUT
    assert client.seen["a_exists"] and client.seen["b_exists"]


def test_output_vs_output_with_neutral_field_names(client):
    r = client.post("/compare", data={"comparison_mode": "output_vs_output"},
                    files={"pdf_a": _pdf("a.pdf"), "pdf_b": _pdf("b.pdf")})

    assert r.status_code == 200
    assert r.json() == {"ok": True, "mode": "output_vs_output"}


def test_neutral_names_take_precedence_over_legacy(client):
    files = {"client_pdf": _pdf(data=PDF + b"legacy-1"), "output_pdf": _pdf(data=PDF + b"legacy-2"),
             "pdf_a": _pdf(data=PDF + b"A"), "pdf_b": _pdf(data=PDF + b"B")}
    client.post("/compare", files=files)

    assert client.seen["a_bytes"].endswith(b"A") and client.seen["b_bytes"].endswith(b"B")
    # temp files are removed once the request is done
    assert not os.path.exists(client.seen["a"]) and not os.path.exists(client.seen["b"])


def test_unknown_mode_is_rejected(client):
    r = client.post("/compare", data={"comparison_mode": "nope"},
                    files={"pdf_a": _pdf(), "pdf_b": _pdf()})
    assert r.status_code == 422
    assert "output_vs_output" in r.json()["detail"]


def test_missing_second_file_names_the_slot_for_the_mode(client):
    r = client.post("/compare", data={"comparison_mode": "output_vs_output"},
                    files={"pdf_a": _pdf()})
    assert r.status_code == 422
    assert "Output PDF B" in r.json()["detail"] and "Template" not in r.json()["detail"]

    r = client.post("/compare", files={"client_pdf": _pdf()})
    assert r.status_code == 422
    assert "Output PDF" in r.json()["detail"]


def test_non_pdf_upload_is_a_400_not_a_500(client):
    r = client.post("/compare", data={"comparison_mode": "output_vs_output"},
                    files={"pdf_a": _pdf(), "pdf_b": _pdf("b.pdf", b"not a pdf")})
    assert r.status_code == 400
    assert "Output PDF B" in r.json()["detail"]


def test_server_errors_do_not_leak_temp_paths(client, monkeypatch):
    def explode(a_path, b_path, mode):
        raise Exception(f"cannot open {a_path}")

    monkeypatch.setattr(app_module, "compare_pdfs", explode)
    r = client.post("/compare", files={"client_pdf": _pdf(), "output_pdf": _pdf()})

    assert r.status_code == 500
    assert "/tmp" not in r.json()["detail"] and ".pdf" not in r.json()["detail"].replace("<uploaded PDF>", "")
    assert "<uploaded PDF>" in r.json()["detail"]


def test_unauthenticated_requests_are_still_rejected():
    app_module.app.dependency_overrides.clear()
    r = TestClient(app_module.app).post("/compare", files={"client_pdf": _pdf(), "output_pdf": _pdf()})
    assert r.status_code == 401
