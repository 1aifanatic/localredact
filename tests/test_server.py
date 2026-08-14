import pymupdf
import pytest
from fastapi.testclient import TestClient

from localredact.server import create_app, main


def pdf_bytes(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def test_health_describes_local_processing():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "local_processing": True}


def test_about_endpoint_discloses_license_and_source():
    with TestClient(create_app()) as client:
        response = client.get("/v1/about")

    assert response.status_code == 200
    assert response.json() == {
        "name": "LocalRedact",
        "license": "AGPL-3.0-only",
        "source": "https://github.com/1aifanatic/localredact",
        "warranty": "This software is provided without warranty.",
    }


def test_service_returns_an_applied_redacted_pdf():
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/redact",
            files={
                "document": ("input.pdf", pdf_bytes("Email service@example.com"), "application/pdf")
            },
            data={"instruction": "Redact email addresses"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-redaction-count"] == "1"
    with pymupdf.open(stream=response.content, filetype="pdf") as document:
        assert "service@example.com" not in document[0].get_text()


def test_service_rejects_an_unknown_target_without_echoing_document_text():
    secret = "document-secret@example.com"
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/redact",
            files={"document": ("input.pdf", pdf_bytes(secret), "application/pdf")},
            data={"instruction": "Redact unicorn IDs"},
        )

    assert response.status_code == 422
    assert secret not in response.text


def test_server_refuses_network_bind_without_explicit_opt_in():
    with pytest.raises(SystemExit) as stopped:
        main(["--host", "0.0.0.0"])

    assert stopped.value.code == 2
