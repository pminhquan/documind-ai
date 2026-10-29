"""D-22: malformed evaluation payloads fail cleanly without corrupting metrics."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from documind.evaluation.cli import main
from documind.evaluation.invoice_eval import evaluate_manifest as eval_invoices
from documind.evaluation.manifest import ManifestEntry
from documind.evaluation.table_eval import evaluate_manifest as eval_tables

MISSING = object()

TRUTH_TABLE = {"rows": 1, "columns": 1, "cells": [["A"]]}
PRED_TABLE = {
    "table_id": "table_0",
    "rows": 1,
    "columns": 1,
    "cells": [{"row_index": 0, "column_index": 0, "text": "A"}],
}
FULL_INVOICE = {
    "supplier": "ACME",
    "invoice_number": "1",
    "invoice_date": "2026-01-01",
    "currency": "USD",
    "subtotal": "10.00",
    "tax": "1.00",
    "discount": None,
    "total": "11.00",
    "payment_amount": None,
    "change_amount": None,
    "line_items": [{"description": "SOAP", "line_total": "10.00"}],
}


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def fake_manifest(entries):
    return type("M", (), {"entries": entries})()


def invoice_entry(tmp_path: Path, doc_id, truth_invoice, pred_invoice):
    gt = write_json(tmp_path / "gt" / f"{doc_id}.json",
                    {"id": doc_id, "invoice": truth_invoice})
    pred = write_json(tmp_path / "pred" / f"{doc_id}.json",
                      {"invoice": pred_invoice})
    return ManifestEntry(doc_id, pred, gt)


def table_entry(tmp_path: Path, doc_id, truth_tables, pred_tables):
    gt = write_json(tmp_path / "gt" / f"{doc_id}.json",
                    {"id": doc_id, "tables": truth_tables})
    pred = write_json(tmp_path / "pred" / f"{doc_id}.json",
                      {"tables": pred_tables})
    return ManifestEntry(doc_id, pred, gt)


def table_with(rows=MISSING, columns=MISSING, cells=MISSING):
    table = {}
    if rows is not MISSING:
        table["rows"] = rows
    if columns is not MISSING:
        table["columns"] = columns
    if cells is not MISSING:
        table["cells"] = cells
    return table


class TestInvoiceObjectValidation:
    @pytest.mark.parametrize("role", ["ground_truth", "prediction"])
    @pytest.mark.parametrize("bad", ["invalid", [1, 2], 123, True, False, 0, ""])
    def test_non_object_invoice_rejected(self, tmp_path, role, bad):
        truth = bad if role == "ground_truth" else FULL_INVOICE
        pred = bad if role == "prediction" else FULL_INVOICE
        entry = invoice_entry(tmp_path, "doc", truth, pred)
        with pytest.raises(ValueError, match="'invoice' must be an object"):
            eval_invoices(fake_manifest([entry]))

    def test_null_invoice_is_treated_as_empty_object(self, tmp_path):
        entry = invoice_entry(tmp_path, "doc", None, None)
        summary = eval_invoices(fake_manifest([entry]))
        doc = summary["documents"][0]
        assert doc["summary"]["accuracy"] is None
        assert doc["line_items"]["item_precision"] is None


class TestInvoiceLineItemsValidation:
    @pytest.mark.parametrize("role", ["ground_truth", "prediction"])
    @pytest.mark.parametrize("bad", ["invalid", {"0": {}}, 123, True, False, ""])
    def test_non_list_container_rejected(self, tmp_path, role, bad):
        truth = {**FULL_INVOICE, "line_items": bad}
        pred = FULL_INVOICE if role == "ground_truth" else truth
        if role == "prediction":
            truth = FULL_INVOICE
        entry = invoice_entry(tmp_path, "doc", truth, pred)
        with pytest.raises(ValueError, match=r"'invoice\.line_items' must be a list"):
            eval_invoices(fake_manifest([entry]))

    @pytest.mark.parametrize("role", ["ground_truth", "prediction"])
    @pytest.mark.parametrize("bad", [["COFFEE"], [123], [None], [["nested"]]])
    def test_non_object_item_rejected(self, tmp_path, role, bad):
        truth = {**FULL_INVOICE, "line_items": bad}
        pred = FULL_INVOICE if role == "ground_truth" else truth
        if role == "prediction":
            truth = FULL_INVOICE
        entry = invoice_entry(tmp_path, "doc", truth, pred)
        with pytest.raises(
            ValueError, match=r"'invoice\.line_items\[0\]' must be an object"
        ):
            eval_invoices(fake_manifest([entry]))

    def test_null_line_items_is_treated_as_empty(self, tmp_path):
        truth = {**FULL_INVOICE, "line_items": None}
        entry = invoice_entry(tmp_path, "doc", truth, truth)
        line_items = eval_invoices(fake_manifest([entry]))["documents"][0]["line_items"]
        assert line_items["expected_items"] == 0
        assert line_items["item_precision"] is None


class TestEmptyDocuments:
    def test_empty_invoice_is_valid(self, tmp_path):
        entry = invoice_entry(tmp_path, "empty", {}, {})
        summary = eval_invoices(fake_manifest([entry]))["documents"][0]
        assert summary["summary"]["accuracy"] is None
        assert summary["line_items"]["item_precision"] is None

    def test_empty_table_lists_are_valid(self, tmp_path):
        entry = table_entry(tmp_path, "empty", [], [])
        outcome = eval_tables(fake_manifest([entry]))["documents"][0]
        assert outcome["tables_expected"] == 0
        assert outcome["tables_predicted"] == 0


class TestTableContainerValidation:
    @pytest.mark.parametrize("role", ["ground_truth", "prediction"])
    @pytest.mark.parametrize("bad", ["invalid", {"rows": 1}, 123, True, False, ""])
    def test_non_list_tables_container_rejected(self, tmp_path, role, bad):
        truth = bad if role == "ground_truth" else [TRUTH_TABLE]
        pred = bad if role == "prediction" else [PRED_TABLE]
        entry = table_entry(tmp_path, "doc", truth, pred)
        with pytest.raises(ValueError, match="'tables' must be a list"):
            eval_tables(fake_manifest([entry]))

    @pytest.mark.parametrize("role", ["ground_truth", "prediction"])
    @pytest.mark.parametrize("bad", [[None], [123], ["table"]])
    def test_non_object_table_rejected(self, tmp_path, role, bad):
        truth = bad if role == "ground_truth" else [TRUTH_TABLE]
        pred = bad if role == "prediction" else [PRED_TABLE]
        entry = table_entry(tmp_path, "doc", truth, pred)
        with pytest.raises(ValueError, match=r"'tables\[0\]' must be an object"):
            eval_tables(fake_manifest([entry]))


class TestTableDimensionsValidation:
    @pytest.mark.parametrize("role", ["ground_truth", "prediction"])
    @pytest.mark.parametrize("field", ["rows", "columns"])
    @pytest.mark.parametrize(
        "bad", [MISSING, None, "abc", "2", True, False, -1, 2.5, {}, []]
    )
    def test_invalid_dimension_rejected(self, tmp_path, role, field, bad):
        broken = dict(TRUTH_TABLE)
        if bad is MISSING:
            broken.pop(field)
        else:
            broken[field] = bad
        if role == "ground_truth":
            entry = table_entry(tmp_path, "doc", [broken], [PRED_TABLE])
        else:
            broken["table_id"] = "table_0"
            broken["cells"] = PRED_TABLE["cells"]
            entry = table_entry(tmp_path, "doc", [TRUTH_TABLE], [broken])
        with pytest.raises(
            ValueError, match=rf"'tables\[0\]\.{field}' must be a non-negative integer"
        ):
            eval_tables(fake_manifest([entry]))

    def test_valid_shape_mismatch_is_still_scored(self, tmp_path):
        truth = {"rows": 2, "columns": 2, "cells": [["A", "B"], ["C", "D"]]}
        pred = {**PRED_TABLE, "rows": 1, "columns": 2,
                "cells": [{"row_index": 0, "column_index": 0, "text": "A"},
                          {"row_index": 0, "column_index": 1, "text": "B"}]}
        entry = table_entry(tmp_path, "doc", [truth], [pred])
        comparison = eval_tables(fake_manifest([entry]))["documents"][0]["comparisons"][0]
        assert comparison["structure_ok"] is False
        assert comparison["missing_cells"] == 2


class TestTableCellContainerValidation:
    @pytest.mark.parametrize(
        "bad, message",
        [
            ("A", r"'tables\[0\]\.cells' must be a list"),
            ({"0": "A"}, r"'tables\[0\]\.cells' must be a list"),
            ([123], r"'tables\[0\]\.cells\[0\]' must be a list"),
            ([["A"], None], r"'tables\[0\]\.cells\[1\]' must be a list"),
        ],
    )
    def test_invalid_truth_cells_rejected(self, tmp_path, bad, message):
        truth = table_with(1, 1, bad)
        entry = table_entry(tmp_path, "doc", [truth], [PRED_TABLE])
        with pytest.raises(ValueError, match=message):
            eval_tables(fake_manifest([entry]))

    @pytest.mark.parametrize(
        "bad, message",
        [
            ("A", r"'tables\[0\]\.cells' must be a list"),
            ({"0": "A"}, r"'tables\[0\]\.cells' must be a list"),
            ([None], r"'tables\[0\]\.cells\[0\]' must be an object"),
            ([123], r"'tables\[0\]\.cells\[0\]' must be an object"),
            (["A"], r"'tables\[0\]\.cells\[0\]' must be an object"),
        ],
    )
    def test_invalid_prediction_cells_rejected(self, tmp_path, bad, message):
        pred = {**PRED_TABLE, "cells": bad}
        entry = table_entry(tmp_path, "doc", [TRUTH_TABLE], [pred])
        with pytest.raises(ValueError, match=message):
            eval_tables(fake_manifest([entry]))

    def test_null_or_missing_cells_is_treated_as_empty(self, tmp_path):
        for truth_cells, pred_cells in ((None, None), (MISSING, MISSING)):
            truth = table_with(1, 1, truth_cells)
            pred = {**PRED_TABLE}
            if pred_cells is MISSING:
                pred.pop("cells")
            else:
                pred["cells"] = pred_cells
            entry = table_entry(
                tmp_path, f"doc-{truth_cells is MISSING}", [truth], [pred]
            )
            comparison = eval_tables(
                fake_manifest([entry])
            )["documents"][0]["comparisons"][0]
            assert comparison["cells_matched"] == 0
            assert comparison["missing_cells"] == 1

    def test_invalid_coordinates_still_score_as_extra(self, tmp_path):
        pred = {**PRED_TABLE, "cells": [
            {"row_index": "wrong", "column_index": 0, "text": "A"},
        ]}
        entry = table_entry(tmp_path, "doc", [TRUTH_TABLE], [pred])
        comparison = eval_tables(fake_manifest([entry]))["documents"][0]["comparisons"][0]
        assert comparison["extra_cells"] == 1
        assert comparison["missing_cells"] == 1
        assert len(comparison["issues"]) == 1


class TestUnmatchedTableValidation:
    def test_malformed_extra_predicted_table_rejected(self, tmp_path):
        bad = table_with(1, 1, [None])
        entry = table_entry(tmp_path, "doc", [TRUTH_TABLE],
                            [PRED_TABLE, bad])
        with pytest.raises(ValueError, match=r"'tables\[1\]\.cells\[0\]' must be an object"):
            eval_tables(fake_manifest([entry]))

    def test_malformed_missed_truth_table_rejected(self, tmp_path):
        bad = table_with(1, 1, [None])
        entry = table_entry(tmp_path, "doc", [TRUTH_TABLE, bad], [PRED_TABLE])
        with pytest.raises(ValueError, match=r"'tables\[1\]\.cells\[0\]' must be a list"):
            eval_tables(fake_manifest([entry]))

    def test_malformed_second_document_rejected(self, tmp_path):
        good = table_entry(tmp_path, "good", [TRUTH_TABLE], [PRED_TABLE])
        bad = table_entry(tmp_path, "bad", [table_with(None, 1, [["A"]])],
                          [PRED_TABLE])
        with pytest.raises(ValueError, match="non-negative integer"):
            eval_tables(fake_manifest([good, bad]))

    def test_invalid_dimensions_on_extra_predicted_table_rejected(self, tmp_path):
        bad = {"table_id": "bad", "rows": None, "columns": 1, "cells": []}
        entry = table_entry(tmp_path, "doc", [TRUTH_TABLE],
                            [PRED_TABLE, bad])
        with pytest.raises(
            ValueError,
            match=r"'tables\[1\]\.rows' must be a non-negative integer",
        ):
            eval_tables(fake_manifest([entry]))

    def test_invalid_dimensions_on_missed_truth_table_rejected(self, tmp_path):
        bad = {"rows": 1, "columns": None, "cells": [["A"]]}
        entry = table_entry(tmp_path, "doc", [TRUTH_TABLE, bad],
                            [PRED_TABLE])
        with pytest.raises(
            ValueError,
            match=r"'tables\[1\]\.columns' must be a non-negative integer",
        ):
            eval_tables(fake_manifest([entry]))


class TestCliMalformedInput:
    @staticmethod
    def _manifest(tmp_path, task, documents):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({"task": task, "documents": documents}),
                        encoding="utf-8")
        return path

    @pytest.mark.parametrize("bad", ["invalid", [1, 2], 123, True, False])
    def test_invoice_malformed_returns_clean_error(self, tmp_path, capsys, bad):
        entry = invoice_entry(tmp_path, "bad", bad, FULL_INVOICE)
        manifest = self._manifest(tmp_path, "invoice", [{
            "id": "bad", "prediction": str(entry.prediction),
            "ground_truth": str(entry.ground_truth),
        }])
        output = tmp_path / "out"
        code = main(["--manifest", str(manifest), "--output", str(output)])
        err = capsys.readouterr().err
        assert code == 2
        assert "Evaluation error:" in err
        assert "'invoice' must be an object" in err
        assert "Traceback" not in err
        assert not (output / "summary.json").exists()
        assert not (output / "report.md").exists()

    def test_table_malformed_returns_clean_error(self, tmp_path, capsys):
        entry = table_entry(tmp_path, "bad",
                            [table_with(1, 1, [None])], [PRED_TABLE])
        manifest = self._manifest(tmp_path, "table", [{
            "id": "bad", "prediction": str(entry.prediction),
            "ground_truth": str(entry.ground_truth),
        }])
        output = tmp_path / "out"
        code = main(["--manifest", str(manifest), "--output", str(output)])
        err = capsys.readouterr().err
        assert code == 2
        assert "Evaluation error:" in err
        assert "tables[0].cells[0]' must be a list" in err
        assert "Traceback" not in err
        assert not (output / "summary.json").exists()

    def test_subprocess_reports_clean_error(self, tmp_path):
        entry = invoice_entry(tmp_path, "bad", "invalid", FULL_INVOICE)
        manifest = self._manifest(tmp_path, "invoice", [{
            "id": "bad", "prediction": str(entry.prediction),
            "ground_truth": str(entry.ground_truth),
        }])
        repo_root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env["PYTHONPATH"] = str(repo_root / "src") + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        proc = subprocess.run(
            [sys.executable, "-m", "documind.evaluation.cli",
             "--manifest", str(manifest), "--output", str(tmp_path / "out")],
            cwd=repo_root, env=env, capture_output=True, text=True,
            encoding="utf-8",
        )
        assert proc.returncode == 2
        assert "Evaluation error:" in proc.stderr
        assert "'invoice' must be an object" in proc.stderr
        assert "Traceback" not in proc.stderr
        assert not (tmp_path / "out" / "summary.json").exists()

    def test_failed_eval_preserves_existing_reports(self, tmp_path, capsys):
        out = tmp_path / "out"
        out.mkdir()
        (out / "summary.json").write_text('{"old": true}', encoding="utf-8")
        (out / "report.md").write_text("old report", encoding="utf-8")
        entry = invoice_entry(tmp_path, "bad", "invalid", FULL_INVOICE)
        manifest = self._manifest(tmp_path, "invoice", [{
            "id": "bad", "prediction": str(entry.prediction),
            "ground_truth": str(entry.ground_truth),
        }])
        assert main(["--manifest", str(manifest), "--output", str(out)]) == 2
        capsys.readouterr()
        assert (out / "summary.json").read_text(encoding="utf-8") == '{"old": true}'
        assert (out / "report.md").read_text(encoding="utf-8") == "old report"

    def test_malformed_last_document_publishes_nothing(self, tmp_path, capsys):
        good1 = invoice_entry(tmp_path, "good1", FULL_INVOICE, FULL_INVOICE)
        good2 = invoice_entry(tmp_path, "good2", FULL_INVOICE, FULL_INVOICE)
        bad = invoice_entry(tmp_path, "bad-last", "invalid", FULL_INVOICE)
        manifest = self._manifest(tmp_path, "invoice", [{
            "id": e.id, "prediction": str(e.prediction),
            "ground_truth": str(e.ground_truth),
        } for e in (good1, good2, bad)])
        output = tmp_path / "out"
        code = main(["--manifest", str(manifest), "--output", str(output)])
        captured = capsys.readouterr()
        assert code == 2
        assert "Evaluation error:" in captured.err
        assert "bad-last.json" in captured.err
        assert "Traceback" not in captured.err
        assert "Task:" not in captured.out
        assert not (output / "summary.json").exists()
        assert not (output / "report.md").exists()

    def test_error_does_not_echo_document_contents(self, tmp_path, capsys):
        secret = "SECRET-CUSTOMER-NAME"
        entry = invoice_entry(tmp_path, "bad", secret, FULL_INVOICE)
        manifest = self._manifest(tmp_path, "invoice", [{
            "id": "bad", "prediction": str(entry.prediction),
            "ground_truth": str(entry.ground_truth),
        }])
        assert main(["--manifest", str(manifest), "--output",
                     str(tmp_path / "out")]) == 2
        err = capsys.readouterr().err
        assert "Evaluation error:" in err
        assert "'invoice' must be an object" in err
        assert secret not in err
        assert "Traceback" not in err

    def test_multi_document_failure_publishes_nothing(self, tmp_path, capsys):
        good = invoice_entry(tmp_path, "good1", FULL_INVOICE, FULL_INVOICE)
        bad = invoice_entry(tmp_path, "bad", "invalid", FULL_INVOICE)
        good2 = invoice_entry(tmp_path, "good2", FULL_INVOICE, FULL_INVOICE)
        manifest = self._manifest(tmp_path, "invoice", [{
            "id": e.id, "prediction": str(e.prediction),
            "ground_truth": str(e.ground_truth),
        } for e in (good, bad, good2)])
        output = tmp_path / "out"
        code = main(["--manifest", str(manifest), "--output", str(output)])
        captured = capsys.readouterr()
        assert code == 2
        assert "Evaluation error:" in captured.err
        assert "bad.json" in captured.err
        assert "Traceback" not in captured.err
        assert "Task:" not in captured.out
        assert not (output / "summary.json").exists()
        assert not (output / "report.md").exists()
