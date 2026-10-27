"""D-18: PDF page-level exports, corrections, resets, and batch ZIP.

Drives the real ``static/app.js`` in a Node DOM harness (page tabs, input
edits, Reset buttons) and feeds the resulting export payloads to the real
FastAPI export endpoint, reading CSV/XLSX/ZIP artifacts back. Assertions
are behavioral: they check what a user would see or download, not how the
frontend is implemented.
"""

import csv
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from documind.web.app import create_app

APP_JS = Path(__file__).parent.parent / "src" / "documind" / "web" / "static" / "app.js"
HARNESS = Path(__file__).parent / "fixtures" / "frontend" / "pdf_page_harness.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed")


@pytest.fixture(scope="module")
def scenarios():
    result = subprocess.run(
        ["node", str(HARNESS), str(APP_JS)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"frontend harness failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)["scenarios"]


@pytest.fixture
def client():
    return TestClient(create_app())


def scenario_data(scenarios, name):
    entry = scenarios[name]
    assert entry["ok"], entry.get("error")
    return entry["data"]


def invoice_data(payload):
    """machine_output is the full InvoiceResponse; this is its InvoiceData."""
    return payload["data"]["machine_output"]["invoice"]


def invoice_csv_values(content: bytes) -> dict[str, str]:
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    return dict(rows[1:11])


def invoice_xlsx_values(content: bytes) -> dict[str, str]:
    from openpyxl import load_workbook

    sheet = load_workbook(io.BytesIO(content))["Invoice"]
    return {
        sheet.cell(row=row, column=1).value: sheet.cell(row=row, column=2).value
        for row in range(1, 11)
    }


def export(client, payload):
    response = client.post("/api/export", json=payload)
    assert response.status_code == 200, response.text
    return response


class TestScenarioATwoPagePdf:
    """Corrections survive page switches and are visible with markers."""

    def test_page_switch_restores_corrections(self, scenarios):
        data = scenario_data(scenarios, "A")
        assert data["initial"]["total"] == "10.00"
        assert data["initial"]["cell"] == "10"
        assert data["initial"]["tabs"] == 2
        assert data["initial"]["activePageIndex"] == 0
        assert data["initial"]["activeDocKey"] == "document.pdf#0"

        assert data["page1"]["total"] == "20.00"
        assert data["page1"]["cell"] == "20"
        assert data["page1"]["activePageIndex"] == 1
        assert data["page1"]["activeDocKey"] == "document.pdf#1"

        assert data["page0Again"]["total"] == "100.00"
        assert data["page0Again"]["cell"] == "Apple"
        assert data["page0Again"]["totalEdited"] is True
        assert data["page0Again"]["cellEdited"] is True

        assert data["page1Again"]["total"] == "200.00"
        assert data["page1Again"]["cell"] == "Orange"
        assert data["page1Again"]["totalEdited"] is True
        assert data["page1Again"]["cellEdited"] is True

        assert data["corrections"]["document.pdf#0"] == {
            "invoice.total": "100.00",
            "tables[0].cells[0][0]": "Apple",
        }
        assert data["corrections"]["document.pdf#1"] == {
            "invoice.total": "200.00",
            "tables[0].cells[0][0]": "Orange",
        }


class TestScenarioBExportIsolation:
    """Each page exports its own machine output plus its own corrections."""

    def test_invoice_csv_is_page_local_and_not_empty(self, scenarios, client):
        data = scenario_data(scenarios, "B")["invoiceCsv"]
        page0, page1 = data["page0"], data["page1"]
        assert page0["filename"] == "document-page-1-invoice.csv"
        assert page1["filename"] == "document-page-2-invoice.csv"
        assert invoice_data(page0)["supplier"] == "SHOP-A"
        assert invoice_data(page0)["total"] == "10.00"
        assert page0["data"]["user_corrections"] == {"total": "100.00"}
        assert invoice_data(page1)["supplier"] == "SHOP-B"
        assert invoice_data(page1)["total"] == "20.00"
        assert page1["data"]["user_corrections"] == {"total": "200.00"}

        values0 = invoice_csv_values(export(client, page0).content)
        assert values0["supplier"] == "SHOP-A"
        assert values0["total"] == "100.00"

        values1 = invoice_csv_values(export(client, page1).content)
        assert values1["supplier"] == "SHOP-B"
        assert values1["total"] == "200.00"

        response = export(client, page0)
        assert "document-page-1-invoice.csv" in response.headers["content-disposition"]

    def test_invoice_xlsx_reads_back_page_local(self, scenarios, client):
        data = scenario_data(scenarios, "B")["invoiceXlsx"]
        values0 = invoice_xlsx_values(export(client, data["page0"]).content)
        assert values0["supplier"] == "SHOP-A"
        assert values0["total"] == "100.00"
        values1 = invoice_xlsx_values(export(client, data["page1"]).content)
        assert values1["supplier"] == "SHOP-B"
        assert values1["total"] == "200.00"

    def test_table_csv_and_xlsx_apply_page_corrections(self, scenarios, client):
        data = scenario_data(scenarios, "B")
        csv0 = export(client, data["tableCsv"]["page0"]).content
        csv1 = export(client, data["tableCsv"]["page1"]).content
        assert list(csv.reader(io.StringIO(csv0.decode("utf-8")))) == [["Apple"]]
        assert list(csv.reader(io.StringIO(csv1.decode("utf-8")))) == [["Orange"]]

        from openpyxl import load_workbook

        xlsx0 = export(client, data["tableXlsx"]["page0"]).content
        xlsx1 = export(client, data["tableXlsx"]["page1"]).content
        assert load_workbook(io.BytesIO(xlsx0))["table_0"]["A1"].value == "Apple"
        assert load_workbook(io.BytesIO(xlsx1))["table_0"]["A1"].value == "Orange"

    def test_json_exports_keep_machine_output_and_corrections_separate(
            self, scenarios, client):
        data = scenario_data(scenarios, "B")
        for page_key, supplier, total, correction in (
                ("page0", "SHOP-A", "10.00", "100.00"),
                ("page1", "SHOP-B", "20.00", "200.00")):
            invoice_payload = data["invoiceJson"][page_key]
            body = export(client, invoice_payload).json()
            assert body["machine_output"]["invoice"]["supplier"] == supplier
            assert body["machine_output"]["invoice"]["total"] == total
            assert body["user_corrections"] == {"total": correction}

            table_payload = data["tableJson"][page_key]
            body = export(client, table_payload).json()
            machine_cell = body["machine_output"]["tables"][0]["cells"][0]["text"]
            assert machine_cell == total.split(".")[0]
            assert body["user_corrections"] == {
                "tables[0].cells[0][0]": "Apple" if page_key == "page0" else "Orange"}

    def test_ocr_exports_use_selected_page(self, scenarios, client):
        data = scenario_data(scenarios, "B")
        for page_key, page_number, text in (
                ("page0", 1, "A TOTAL 10.00"),
                ("page1", 2, "B TOTAL 20.00")):
            ocr_json = data["ocrJson"][page_key]
            assert ocr_json["filename"] == f"document-page-{page_number}-ocr.json"
            assert ocr_json["data"]["full_text"] == text
            assert export(client, ocr_json).json()["full_text"] == text

            ocr_txt = data["ocrTxt"][page_key]
            assert ocr_txt["filename"] == f"document-page-{page_number}-ocr.txt"
            assert export(client, ocr_txt).content == text.encode("utf-8")


class TestScenarioCResetIsolation:
    """Reset is page-local and never touches the other correction family."""

    def test_reset_invoice_keeps_table_and_other_page(self, scenarios):
        data = scenario_data(scenarios, "C")
        page0 = data["page0AfterInvoiceReset"]
        assert page0["total"] == "10.00"
        assert page0["totalEdited"] is False
        assert page0["cell"] == "Apple"
        assert page0["cellEdited"] is True
        assert page0["corrections"] == {"tables[0].cells[0][0]": "Apple"}

        page1 = data["page1AfterPage0Reset"]
        assert page1["total"] == "200.00"
        assert page1["cell"] == "Orange"
        assert page1["corrections"] == {
            "invoice.total": "200.00",
            "tables[0].cells[0][0]": "Orange",
        }

    def test_reset_tables_keeps_invoice_and_exports_machine_values(
            self, scenarios, client):
        data = scenario_data(scenarios, "C")["page1AfterTablesReset"]
        assert data["total"] == "200.00"
        assert data["totalEdited"] is True
        assert data["cell"] == "20"
        assert data["cellEdited"] is False
        assert data["corrections"] == {"invoice.total": "200.00"}

        invoice_payload = data["invoicePayload"]
        assert invoice_payload["filename"] == "document-page-2-invoice.csv"
        values = invoice_csv_values(export(client, invoice_payload).content)
        assert values["supplier"] == "SHOP-B"
        assert values["total"] == "200.00"

        table_csv = list(csv.reader(io.StringIO(
            export(client, data["tablePayload"]).content.decode("utf-8"))))
        assert table_csv == [["20"]]

        page0 = scenario_data(scenarios, "C")["page0Final"]
        assert page0["cell"] == "Apple"
        assert page0["corrections"] == {"tables[0].cells[0][0]": "Apple"}


class TestScenarioDPartialPdfFailure:
    """A failed page is not selectable and never gets fabricated data."""

    def test_failed_page_skipped_and_metadata_preserved(
            self, scenarios, client):
        data = scenario_data(scenarios, "D")
        assert data["tabCount"] == 1
        assert data["tabLabels"] == ["Page 2"]
        assert data["activePageIndex"] == 1
        assert data["activeDocKey"] == "document.pdf#1"
        assert data["total"] == "20.00"

        payload = data["invoicePayload"]
        assert payload["filename"] == "document-page-2-invoice.csv"
        assert invoice_data(payload)["supplier"] == "SHOP-B"
        assert invoice_csv_values(export(client, payload).content)["supplier"] == "SHOP-B"

        batch = data["batch"]
        assert batch is not None
        files = batch["data"]["files"]
        assert len(files) == 1
        pdf = files[0]["data"]
        assert pdf["errors"] == ["page 0: boom"]
        failed_page = pdf["pages"][0]
        assert failed_page == {"page_index": 0, "error": "boom"}
        assert set(failed_page) == {"page_index", "error"}  # no fake OCR/invoice/tables
        succeeded = pdf["pages"][1]
        assert succeeded["page_index"] == 1
        assert succeeded["invoice"]["invoice"]["supplier"] == "SHOP-B"

        response = export(client, batch)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            archived = json.loads(archive.read("document.json"))
        assert archived["pages"][0] == {"page_index": 0, "error": "boom"}
        assert archived["pages"][1]["invoice"]["invoice"]["supplier"] == "SHOP-B"


class TestScenarioESingleImageRegression:
    """Image results keep the pre-D-18 payload shapes and filenames."""

    def test_image_workflow_unchanged(self, scenarios, client):
        data = scenario_data(scenarios, "E")
        initial = data["initial"]
        assert initial["total"] == "9.57"
        assert initial["cell"] == "9.57"
        assert initial["pagesHidden"] is True
        assert initial["activePageIndex"] is None
        assert initial["activeDocKey"] == "scan.png#0"

        invoice_csv = data["invoiceCsv"]
        assert invoice_csv["filename"] == "invoice-result.csv"
        assert invoice_csv["data"]["user_corrections"] == {"total": "10.00"}
        assert invoice_data(invoice_csv)["total"] == "9.57"
        values = invoice_csv_values(export(client, invoice_csv).content)
        assert values["supplier"] == "MINIMART"
        assert values["total"] == "10.00"

        assert data["invoiceJson"]["filename"] == "invoice-result.json"
        assert data["tableCsv"]["filename"] == "tables.csv"
        assert data["tableCsv"]["data"]["user_corrections"] == {
            "tables[0].cells[0][0]": "Apple"}
        assert data["ocrJson"]["filename"] == "ocr-result.json"

        table_csv = list(csv.reader(io.StringIO(
            export(client, data["tableCsv"]).content.decode("utf-8"))))
        assert table_csv == [["Apple"]]


class TestScenarioFBatchZip:
    """PDF batch entries keep every page plus corrections; failures stay
    explicit, and separate documents never mix."""

    def test_batch_zip_contains_complete_pdf(self, scenarios, client):
        data = scenario_data(scenarios, "F")
        assert data["available"] is True
        files = data["payload"]["data"]["files"]
        assert len(files) == 3
        by_name = {item["filename"]: item for item in files}
        assert set(by_name) == {"document.json", "scan.json", "batch-errors.json"}

        pdf = by_name["document.json"]["data"]
        assert pdf["kind"] == "pdf"
        assert pdf["page_count"] == 2
        assert [page["page_index"] for page in pdf["pages"]] == [0, 1]
        assert [page["source"] for page in pdf["pages"]] == [
            "upload#page0", "upload#page1"]
        page0, page1 = pdf["pages"]
        assert page0["ocr"]["full_text"] == "A TOTAL 10.00"
        assert page0["invoice"]["invoice"]["supplier"] == "SHOP-A"
        assert page0["tables"]["tables"][0]["cells"][0]["text"] == "10"
        assert page0["user_corrections"] == {
            "invoice.total": "100.00",
            "tables[0].cells[0][0]": "Apple",
        }
        assert page1["ocr"]["full_text"] == "B TOTAL 20.00"
        assert page1["invoice"]["invoice"]["supplier"] == "SHOP-B"
        assert page1["tables"]["tables"][0]["cells"][0]["text"] == "20"
        assert page1["user_corrections"] == {
            "invoice.total": "200.00",
            "tables[0].cells[0][0]": "Orange",
        }

        response = export(client, data["payload"])
        assert response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            assert len(names) == 3
            archived_pdf = json.loads(archive.read("document.json"))
            archived_image = json.loads(archive.read("scan.json"))
            archived_errors = json.loads(archive.read("batch-errors.json"))

        assert archived_pdf["pages"][0]["user_corrections"]["tables[0].cells[0][0]"] == "Apple"
        assert archived_pdf["pages"][1]["user_corrections"]["tables[0].cells[0][0]"] == "Orange"
        assert archived_image["machine_output"]["invoice"]["supplier"] == "MINIMART"
        assert archived_errors == {
            "failed_documents": [{"filename": "broken.png", "error": "boom"}]}


class TestScenarioGRegressions:
    """Previously fixed export hardening stays effective on page payloads."""

    def test_formula_injection_is_blocked_on_page_exports(
            self, scenarios, client):
        data = scenario_data(scenarios, "G")
        invoice_csv = export(client, data["invoiceCsv"]).content
        rows = list(csv.reader(io.StringIO(invoice_csv.decode("utf-8"))))
        assert dict(rows[1:11])["supplier"] == "'=SUM(A1)"

        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(
            export(client, data["invoiceXlsx"]).content))
        cell = workbook["Invoice"]["B1"]
        assert cell.value == "=SUM(A1)"
        assert cell.data_type == "s"  # stored as text, never a formula

        table_csv = export(client, data["tableCsv"]).content
        assert list(csv.reader(io.StringIO(table_csv.decode("utf-8")))) == [["'=cmd()"]]

        table_xlsx = load_workbook(io.BytesIO(
            export(client, data["tableXlsx"]).content))
        sheet = table_xlsx[table_xlsx.sheetnames[0]]
        assert sheet["A1"].value == "=cmd()"
        assert sheet["A1"].data_type == "s"

    def test_table_correction_paths_are_verbatim(self, scenarios, client):
        data = scenario_data(scenarios, "G")
        assert data["tableCsv"]["data"]["user_corrections"] == {
            "tables[0].cells[0][0]": "=cmd()"}
        response = export(client, data["tableCsv"])
        assert response.status_code == 200

    def test_malformed_export_payload_still_422(self, scenarios, client):
        payload = scenario_data(scenarios, "G")["invoiceCsv"]
        payload["data"]["user_corrections"] = {"invoice.evil": "x"}
        response = client.post("/api/export", json=payload)
        assert response.status_code == 422
        assert "Invalid correction path" in response.json()["detail"]


class TestExportErrorPaths:
    def test_missing_page_artifact_raises_clear_error(self, scenarios):
        data = scenario_data(scenarios, "H")
        assert data["invoice-csv"] == {
            "ok": False,
            "message": "Page 1 has no invoice result to export.",
        }
        assert data["table-xlsx"] == {
            "ok": False,
            "message": "Page 1 has no table result to export.",
        }


class TestMultiTablePageExport:
    def test_multi_table_csv_is_named_zip_and_reads_back(self, scenarios,
                                                         client):
        payload = scenario_data(scenarios, "I")["tableCsv"]
        assert payload["filename"] == "multi-page-1-tables.zip"
        response = export(client, payload)
        assert response.headers["content-type"] == "application/zip"
        assert 'filename="multi-page-1-tables.zip"' in \
            response.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert sorted(archive.namelist()) == ["tables_t0.csv", "tables_t1.csv"]


def test_batch_zip_export_has_a_ui_trigger():
    """Regression: buildBatchPayload existed but no control reached it."""
    html = (APP_JS.parent / "index.html").read_text(encoding="utf-8")
    assert 'data-export="batch-zip"' in html

