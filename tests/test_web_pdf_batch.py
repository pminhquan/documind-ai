"""M5B tests: PDF processing, batch ZIP exports, invoice CSV/XLSX."""

import csv
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from raw_pdf_helper import make_pdf_with_two_large_pages, make_raw_pdf

from documind.web import service
from documind.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def mocked_engine(monkeypatch):

    class FakeEngine:
        def __init__(self):
            self.calls = 0

        def predict(self, path):
            self.calls += 1
            return [{
                "rec_texts": ["TOTAL", "13.53"],
                "rec_scores": [0.99, 0.98],
                "rec_polys": [
                    [[1, 1], [20, 1], [20, 10], [1, 10]],
                    [[25, 1], [40, 1], [40, 10], [25, 10]],
                ],
            }]

    engine = FakeEngine()
    monkeypatch.setattr(service, "_get_engine", lambda: engine)
    return engine


def make_pdf(pages: int = 2) -> bytes:
    """Deterministic small multi-page PDF via PIL."""
    buffer = io.BytesIO()
    images = [Image.new("RGB", (60, 40), color="white") for _ in range(pages)]
    images[0].save(buffer, format="PDF", save_all=True,
                   append_images=images[1:], resolution=72)
    return buffer.getvalue()


class TestPdfProcessing:
    def test_two_page_pdf_processed_page_by_page(self, client, mocked_engine):
        response = client.post("/api/process", data={"workflow": "ocr"},
                               files={"upload": ("doc.pdf", make_pdf(2), "application/pdf")})
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "pdf"
        assert body["page_count"] == 2
        assert [page["page_index"] for page in body["pages"]] == [0, 1]
        assert body["pages"][0]["ocr"]["full_text"] == "TOTAL\n13.53"
        assert body["errors"] == []
        assert mocked_engine.calls == 2  # one per page

    def test_malformed_pdf_400(self, client, mocked_engine):
        response = client.post("/api/process", data={"workflow": "ocr"},
                               files={"upload": ("doc.pdf", b"%PDF-not really",
                                                 "application/pdf")})
        assert response.status_code == 400
        assert "Malformed PDF" in response.json()["detail"]

    def test_non_pdf_magic_415(self, client, mocked_engine):
        response = client.post("/api/process", data={"workflow": "ocr"},
                               files={"upload": ("doc.pdf", b"just text",
                                                 "application/pdf")})
        # Not a PDF -> falls through to the image path, which rejects the
        # .pdf extension as unsupported.
        assert response.status_code == 415
        assert "Unsupported file type" in response.json()["detail"]

    def test_page_limit_enforced(self, client, mocked_engine):
        response = client.post("/api/process", data={"workflow": "ocr"},
                               files={"upload": ("doc.pdf", make_pdf(11),
                                                 "application/pdf")})
        assert response.status_code == 400
        assert "limit" in response.json()["detail"]


class TestPdfPreflight:
    """P0.2: reject oversized pages BEFORE allocating the bitmap."""

    def test_huge_mediabox_rejected_preflight(self, tmp_path):
        from documind.web.pdf import PdfError, render_pdf_pages

        # below the 15000pt side cap, but scale 2 -> 14000x14000 px = 196MP
        with pytest.raises(PdfError, match="too large"):
            render_pdf_pages(make_raw_pdf(7000, 7000), tmp_path)
        assert list(tmp_path.iterdir()) == []  # nothing rendered

    def test_point_cap_rejected(self, tmp_path):
        from documind.web.pdf import PdfError, render_pdf_pages

        # a single side beyond the 15000pt cap is unusable
        with pytest.raises(PdfError, match="unusable dimensions"):
            render_pdf_pages(make_raw_pdf(20000, 200), tmp_path)

    def test_normal_page_passes_preflight(self, tmp_path):
        from documind.web.pdf import render_pdf_pages

        paths = render_pdf_pages(make_raw_pdf(200, 100), tmp_path)
        assert [path.name for path in paths] == ["page_000.png"]

    def test_cumulative_budget_enforced(self, tmp_path, monkeypatch):
        import documind.web.pdf as pdf_module

        monkeypatch.setattr(pdf_module, "MAX_PAGE_PIXELS", 2_000_000)
        monkeypatch.setattr(pdf_module, "MAX_TOTAL_PIXELS", 3_000_000)
        # two 1800x900px pages = 1.62MP each; cumulative 3.24MP > 3MP
        with pytest.raises(pdf_module.PdfError, match="pixel budget"):
            pdf_module.render_pdf_pages(make_pdf_with_two_large_pages(), tmp_path)


class TestInvoiceExportHardening:
    """P0.3: XLSX must strip XML-illegal control characters (openpyxl
    raises IllegalCharacterError -> unhandled 500 without this)."""

    def test_control_characters_stripped_not_500(self, client):
        from openpyxl import load_workbook

        response = client.post("/api/export", json={
            "kind": "invoice-xlsx",
            "data": {"invoice": {"supplier": "ACMECORP",
                                 "total": "5.00"}}})
        assert response.status_code == 200
        sheet = load_workbook(io.BytesIO(response.content))["Invoice"]
        values = {sheet.cell(row=r, column=1).value: sheet.cell(row=r, column=2).value
                  for r in range(1, 11)}
        assert values["supplier"] == "ACMECORP"


class TestOcrTxtExport:
    def test_txt_export(self, client):
        response = client.post("/api/export", json={
            "kind": "ocr-txt",
            "data": {"full_text": "TOTAL 13.53\nCASH 15.00"}})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.content == b"TOTAL 13.53\nCASH 15.00"

    def test_missing_full_text_422(self, client):
        response = client.post("/api/export", json={"kind": "ocr-txt", "data": {}})
        assert response.status_code == 422


class TestInvoiceExports:
    @staticmethod
    def _payload():
        invoice = {
            "supplier": "ACME", "total": "11.00", "tax": "1.00",
            "discount": None, "invoice_date": "2026-01-01",
            "line_items": [
                {"description": "=evil()", "quantity": "2",
                 "unit_price": "5.00", "line_total": "10.00"},
            ],
        }
        return {"machine_output": {"invoice": invoice},
                "user_corrections": {"invoice.total": "12.00"}}

    def test_csv_applies_corrections_and_formula_safety(self, client):
        response = client.post("/api/export", json={
            "kind": "invoice-csv", "data": self._payload()})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        values = dict(rows[1:11])
        assert values["total"] == "12.00"          # correction applied
        items_start = rows.index(["Line items"]) + 2
        assert rows[items_start][0] == "'=evil()"  # formula injection guarded

    def test_xlsx_reads_back(self, client):
        from openpyxl import load_workbook

        response = client.post("/api/export", json={
            "kind": "invoice-xlsx", "data": self._payload()})
        assert response.status_code == 200
        sheet = load_workbook(io.BytesIO(response.content))["Invoice"]
        values = {sheet.cell(row=r, column=1).value: sheet.cell(row=r, column=2).value
                  for r in range(1, 11)}
        assert values["total"] == "12.00"

    def test_invalid_correction_path_422(self, client):
        response = client.post("/api/export", json={
            "kind": "invoice-csv",
            "data": {"machine_output": {"invoice": {"total": "1.00"}},
                     "user_corrections": {"invoice.evil": "x"}}})
        assert response.status_code == 422
        assert "Invalid correction path" in response.json()["detail"]


class TestBatchZipExport:
    def test_batch_zip_read_back(self, client):
        payload = {
            "files": [
                {"kind": "ocr-txt", "filename": "doc1.txt",
                 "data": {"full_text": "first document"}},
                {"kind": "invoice-csv", "filename": "doc2.csv",
                 "data": {"invoice": {"supplier": "ACME", "total": "5.00"}}},
            ]
        }
        response = client.post("/api/export", json={"kind": "batch-zip",
                                                    "data": payload})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert sorted(archive.namelist()) == ["doc1.txt", "doc2.csv"]
            assert archive.read("doc1.txt") == b"first document"

    def test_duplicate_names_deduplicated(self, client):
        payload = {"files": [
            {"kind": "ocr-txt", "filename": "same.txt",
             "data": {"full_text": "one"}},
            {"kind": "ocr-txt", "filename": "same.txt",
             "data": {"full_text": "two"}},
        ]}
        response = client.post("/api/export", json={"kind": "batch-zip",
                                                    "data": payload})
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert sorted(archive.namelist()) == ["same.txt", "same_2.txt"]
            assert archive.read("same.txt") == b"one"
            assert archive.read("same_2.txt") == b"two"

    def test_long_duplicate_names_keep_extension(self, client):
        filename = f"{'x' * 78}.txt"
        payload = {"files": [
            {"kind": "ocr-txt", "filename": filename,
             "data": {"full_text": "one"}},
            {"kind": "ocr-txt", "filename": filename,
             "data": {"full_text": "two"}},
        ]}
        response = client.post("/api/export", json={"kind": "batch-zip",
                                                    "data": payload})
        assert response.status_code == 200
        stem = "x" * 73  # 80-char cap leaves room for the extension
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert sorted(archive.namelist()) == [f"{stem}.txt",
                                                  f"{stem}_2.txt"]
            assert archive.read(f"{stem}.txt") == b"one"
            assert archive.read(f"{stem}_2.txt") == b"two"

    def test_too_many_files_422(self, client):
        payload = {"files": [
            {"kind": "ocr-txt", "filename": f"f{i}.txt",
             "data": {"full_text": "x"}} for i in range(11)]
        }
        response = client.post("/api/export", json={"kind": "batch-zip",
                                                    "data": payload})
        assert response.status_code == 422

    def test_invalid_entry_422(self, client):
        payload = {"files": [{"kind": "exe", "filename": "evil.exe", "data": {}}]}
        response = client.post("/api/export", json={"kind": "batch-zip",
                                                    "data": payload})
        assert response.status_code == 422


class TestBatchZipNesting:
    def test_nested_batch_zip_rejected_422(self, client):
        """Regression: batch-zip was a legal INNER entry kind, so a
        client-supplied entry could recurse without any depth limit
        (RecursionError -> 500). Nesting must be rejected with 422."""
        payload = {"files": [
            {"kind": "batch-zip", "filename": "nested.zip",
             "data": {"files": []}},
        ]}
        response = client.post("/api/export",
                               json={"kind": "batch-zip", "data": payload})
        assert response.status_code == 422


class TestPdfResponseSourceSanitization:
    def test_pdf_pages_have_no_temp_path_and_distinct_ids(self, client,
                                                          mocked_engine):
        """D-19: per-page sources are stable upload#pageN labels — never
        server-local render paths; page identity stays with page_index."""
        response = client.post("/api/process",
                               files={"upload": ("doc.pdf", make_pdf(2))},
                               data={"workflow": "auto"})
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "pdf"
        assert [page["page_index"] for page in body["pages"]] == [0, 1]
        sources = [page["source"] for page in body["pages"]]
        assert sources == ["upload#page0", "upload#page1"]
        assert "documind_pdf_" not in response.text
        assert "documind_upload_" not in response.text
