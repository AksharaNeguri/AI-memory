from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.memory import Document, DocumentChunk
from app.services.embeddings import EmbeddingProvider
from app.services.ingestion.extractors import DocxExtractor, PdfExtractor


class TestEmbeddingProvider(EmbeddingProvider):
    model = "test-embedding"
    dimensions = 4

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            float(lowered.count("alpha") + lowered.count("hello")),
            float(lowered.count("pdf") + lowered.count("docx")),
            float(lowered.count("url") + lowered.count("fetched")),
            float(len(lowered.split())),
        ]


@pytest.fixture(autouse=True)
def ingestion_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(
        "app.services.embeddings.get_embedding_provider",
        lambda: TestEmbeddingProvider(),
    )


def test_plain_text_ingestion_persists_document_and_chunks(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    response = client.post(
        "/documents/text",
        headers=auth_headers,
        json={
            "title": "Notes",
            "content": "Alpha   beta\n\n\nGamma delta. " * 80,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["processing_status"] == "COMPLETED"
    assert payload["document_metadata"]["extractor"] == "plain_text"
    assert payload["document_metadata"]["chunk_count"] >= 1
    assert "sha256" in payload["document_metadata"]

    document = db_session.get(Document, UUID(payload["id"]))
    assert document is not None
    assert document.chunks
    assert document.chunks[0].chunk_metadata["start_char"] == 0


def test_file_upload_extracts_markdown_and_saves_original(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    response = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("readme.md", b"# Title\n\nUseful memory text.", "text/markdown")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["original_filename"] == "readme.md"
    assert payload["file_size_bytes"] == len(b"# Title\n\nUseful memory text.")
    assert payload["document_metadata"]["extractor"] == "markdown"
    assert Path(payload["file_path"]).exists()

    chunks = db_session.query(DocumentChunk).filter_by(document_id=UUID(payload["id"])).all()
    assert len(chunks) == 1
    assert "Useful memory text" in chunks[0].content


def test_unsupported_upload_is_rejected(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("archive.bin", b"binary-ish", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type."


def test_upload_size_limit_is_enforced(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 0)

    response = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("notes.txt", b"x", "text/plain")},
    )

    assert response.status_code == 413


def test_document_detail_is_scoped_to_authenticated_user(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    created = client.post(
        "/documents/text",
        headers=auth_headers,
        json={"title": "Private", "content": "Only this user can read this."},
    ).json()

    other_payload = {"email": "other@example.com", "password": "correct-horse-battery"}
    client.post("/auth/register", json=other_payload)
    other_login = client.post(
        "/auth/login",
        data={"username": other_payload["email"], "password": other_payload["password"]},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = client.get(f"/documents/{created['id']}", headers=other_headers)

    assert response.status_code == 404


def test_document_status_endpoint_returns_processing_state(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    created = client.post(
        "/documents/text",
        headers=auth_headers,
        json={"title": "Status", "content": "Status endpoint content."},
    ).json()

    response = client.get(f"/documents/{created['id']}/status", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["processing_status"] == "COMPLETED"
    assert payload["error_message"] is None


def test_docx_extractor_reads_real_docx_xml() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body>
            </w:document>
            """,
        )

    extracted = DocxExtractor().extract(
        buffer.getvalue(),
        filename="sample.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert "Hello DOCX" in extracted.text
    assert extracted.metadata["extractor"] == "docx"


def test_pdf_extractor_reads_pdf_text_operator() -> None:
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 72 720 Td (Hello PDF) Tj ET
endstream
endobj
%%EOF
"""

    extracted = PdfExtractor().extract(pdf, filename="sample.pdf", mime_type="application/pdf")

    assert "Hello PDF" in extracted.text
    assert extracted.metadata["extractor"] in {"pdf-basic", "pypdf"}


def test_url_ingestion_fetches_and_cleans_html(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/page"
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Fetched Title</title></head><body><h1>Hello URL</h1></body></html>",
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    class MockClient:
        def __init__(self, *args, **kwargs) -> None:
            self.client = real_client(transport=transport)

        def __enter__(self):
            return self.client

        def __exit__(self, *args) -> None:
            self.client.close()

    monkeypatch.setattr(httpx, "Client", MockClient)

    response = client.post(
        "/documents/url",
        headers=auth_headers,
        json={"url": "https://example.test/page"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Fetched Title"
    assert payload["source_type"] == "URL"
    assert payload["document_metadata"]["extractor"] == "url"


def test_complete_pdf_upload_embed_store_search_flow(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/Contents 4 0 R>>endobj
4 0 obj<</Length 59>>stream
BT /F1 12 Tf 72 720 Td (Alpha PDF semantic memory chunk) Tj ET
endstream
endobj
%%EOF
"""
    upload = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("memory.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 201
    document = upload.json()
    assert document["processing_status"] == "COMPLETED"

    stored_chunks = db_session.query(DocumentChunk).filter_by(document_id=UUID(document["id"])).all()
    assert stored_chunks
    assert stored_chunks[0].embedding is not None
    assert stored_chunks[0].embedding_model == "test-embedding"

    search = client.post(
        "/search",
        headers=auth_headers,
        json={"query": "alpha pdf", "limit": 5},
    )
    assert search.status_code == 200
    results = search.json()["results"]
    assert results
    assert results[0]["document_id"] == document["id"]
    assert "Alpha PDF" in results[0]["content"]


def test_hybrid_search_adds_keyword_score(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post(
        "/documents/text",
        headers=auth_headers,
        json={"title": "Hybrid", "content": "Alpha keyword semantic content."},
    )

    response = client.post(
        "/search",
        headers=auth_headers,
        json={"query": "alpha keyword", "hybrid": True},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["semantic_score"] is not None
    assert result["keyword_score"] > 0
