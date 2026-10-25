"""Invoice and table evaluation tests (fixtures built in-test)."""

import json
from pathlib import Path

import pytest

from documind.evaluation.invoice_eval import evaluate_manifest as eval_invoices
from documind.evaluation.table_eval import evaluate_manifest as eval_tables
from documind.evaluation.manifest import ManifestEntry


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def invoice_entry(tmp_path: Path, doc_id: str, expected_invoice, predicted_invoice):
    gt = write_json(
        tmp_path / "gt" / f"{doc_id}.json", {"id": doc_id, "invoice": expected_invoice}
    )
    pred = write_json(
        tmp_path / "pred" / f"{doc_id}.json", {"source": "x", "invoice": predicted_invoice}
    )
    return ManifestEntry(id=doc_id, prediction=pred, ground_truth=gt)


FULL_INVOICE = {
    "supplier": "MINI MART EXPRESS",
    "invoice_number": "00001234",
    "invoice_date": "2026-10-25",
    "currency": "USD",
    "subtotal": "12.30",
    "tax": "1.23",
    "discount": None,
    "total": "13.53",
    "payment_amount": "15.00",
    "change_amount": "1.47",
    "line_items": [
        {"description": "SOAP", "quantity": "2", "unit_price": "2.50", "line_total": "5.00"},
        {"description": "MILK 1L", "quantity": "1", "unit_price": "2.50", "line_total": "2.50"},
    ],
}


class TestInvoiceEvaluation:
    def test_perfect_prediction_scores_full(self, tmp_path):
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, FULL_INVOICE)
        summary = eval_invoices(type("M", (), {"entries": [entry], "task": "invoice"})())
        doc = summary["documents"][0]
        assert doc["summary"]["accuracy"] == 1.0
        assert doc["summary"]["missing"] == 0
        assert doc["summary"]["incorrect"] == 0
        assert doc["line_items"]["items_matched"] == 2
        assert summary["aggregate"]["micro_field_accuracy"] == 1.0

    def test_missing_prediction_field_is_error_not_correct(self, tmp_path):
        predicted = {**FULL_INVOICE, "total": None}
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        doc = summary["documents"][0]
        assert doc["fields"]["total"]["status"] == "missing"
        assert doc["summary"]["accuracy"] < 1.0

    def test_incorrect_total_detected(self, tmp_path):
        predicted = {**FULL_INVOICE, "total": "99.99"}
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        assert doc["fields"]["total"]["status"] == "incorrect"

    def test_extra_predicted_field_is_error(self, tmp_path):
        predicted = {**FULL_INVOICE, "tax": "1.23", "discount": "0.50"}
        entry = invoice_entry(
            tmp_path, "doc", FULL_INVOICE, predicted
        )  # GT discount is None
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        assert doc["fields"]["discount"]["status"] == "extra"

    def test_null_on_both_sides_is_true_negative(self, tmp_path):
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, FULL_INVOICE)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        assert doc["fields"]["discount"]["status"] == "true_negative"
        # excluded from the accuracy denominator
        assert doc["summary"]["applicable"] == 9

    def test_money_canonicalization_scale_insensitive(self, tmp_path):
        predicted = {**FULL_INVOICE, "total": "13.530", "subtotal": "12.3"}
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        assert doc["fields"]["total"]["status"] == "matched"
        assert doc["fields"]["subtotal"]["status"] == "matched"

    def test_date_canonicalization(self, tmp_path):
        predicted = {**FULL_INVOICE, "invoice_date": "2026-10-25"}
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        assert doc["fields"]["invoice_date"]["status"] == "matched"
        wrong = {**FULL_INVOICE, "invoice_date": "2026-10-26"}
        entry = invoice_entry(tmp_path, "doc2", FULL_INVOICE, wrong)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        assert doc["fields"]["invoice_date"]["status"] == "incorrect"

    def test_line_item_matching_by_index(self, tmp_path):
        predicted = {
            **FULL_INVOICE,
            "line_items": [
                FULL_INVOICE["line_items"][0],
                {"description": "MILK 2L", "quantity": "1", "unit_price": "2.50",
                 "line_total": "2.50"},
            ],
        }
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        doc = summary["documents"][0]
        assert doc["line_items"]["items_matched"] == 1
        assert doc["line_items"]["items"][1]["fields"]["description"]["status"] == "incorrect"
        assert summary["aggregate"]["item_field_accuracy"] < 1.0

    def test_missing_and_extra_line_items(self, tmp_path):
        predicted = {**FULL_INVOICE, "line_items": [FULL_INVOICE["line_items"][0]]}
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        line_items = summary["documents"][0]["line_items"]
        assert line_items["missing_items"] == 1
        assert line_items["extra_items"] == 0
        assert summary["aggregate"]["missing_line_items"] == 1

        predicted = {**FULL_INVOICE, "line_items": FULL_INVOICE["line_items"] + [
            {"description": "GUM", "quantity": "1", "unit_price": "0.50",
             "line_total": "0.50"},
        ]}
        entry = invoice_entry(tmp_path, "doc2", FULL_INVOICE, predicted)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        assert summary["aggregate"]["extra_line_items"] == 1

    def test_all_null_invoice_accuracy_is_none(self, tmp_path):
        empty = {field: None for field in
                 ("supplier", "invoice_number", "invoice_date", "currency",
                  "subtotal", "tax", "discount", "total", "payment_amount",
                  "change_amount")}
        entry = invoice_entry(tmp_path, "doc", empty, empty)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        doc = summary["documents"][0]
        assert doc["summary"]["accuracy"] is None
        assert summary["aggregate"]["micro_field_accuracy"] is None


class TestItemMetricCorrectness:
    """Regression: line-item quantity/unit_price/line_total were compared
    as strings (so "2.50" != "2.5"), and missing items never lowered the
    reported item score."""

    def predicted_items(self, items):
        return {**FULL_INVOICE, "line_items": items}

    def test_scale_insensitive_item_amounts_match(self, tmp_path):
        predicted = self.predicted_items([
            {"description": "SOAP", "quantity": "2.0", "unit_price": "2.5",
             "line_total": "5.0"},
            {"description": "MILK 1L", "quantity": "1", "unit_price": "2.50",
             "line_total": "2.50"},
        ])
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        doc = summary["documents"][0]
        assert doc["line_items"]["items_matched"] == 2
        assert doc["line_items"]["item_field_accuracy"] == 1.0

    def test_different_item_amount_is_incorrect(self, tmp_path):
        predicted = self.predicted_items([
            {"description": "SOAP", "quantity": "3", "unit_price": "2.50",
             "line_total": "5.00"},
            FULL_INVOICE["line_items"][1],
        ])
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        fields = doc["line_items"]["items"][0]["fields"]
        assert fields["quantity"]["status"] == "incorrect"
        assert doc["line_items"]["items_matched"] == 1

    def test_invalid_and_nonfinite_item_values_never_match(self, tmp_path):
        predicted = self.predicted_items([
            {"description": "SOAP", "quantity": "abc", "unit_price": "NaN",
             "line_total": "Infinity"},
            FULL_INVOICE["line_items"][1],
        ])
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        doc = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]
        fields = doc["line_items"]["items"][0]["fields"]
        assert fields["quantity"]["status"] == "incorrect"
        assert fields["unit_price"]["status"] == "incorrect"
        assert fields["line_total"]["status"] == "incorrect"

    def test_missing_item_shown_by_precision_recall_f1(self, tmp_path):
        # Only the first of two expected items is predicted (perfectly).
        predicted = self.predicted_items([FULL_INVOICE["line_items"][0]])
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        summary = eval_invoices(type("M", (), {"entries": [entry]})())
        line_items = summary["documents"][0]["line_items"]
        assert line_items["item_field_accuracy"] == 1.0  # among matched pairs
        assert line_items["item_precision"] == 1.0
        assert line_items["item_recall"] == 0.5
        assert line_items["item_f1"] == pytest.approx(2 * 0.5 * 1.0 / 1.5)
        assert line_items["missing_items"] == 1
        assert summary["aggregate"]["item_recall"] == 0.5

    def test_extra_item_lowers_precision(self, tmp_path):
        predicted = self.predicted_items(
            FULL_INVOICE["line_items"]
            + [{"description": "GUM", "quantity": "1", "unit_price": "0.50",
                "line_total": "0.50"}]
        )
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        line_items = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]["line_items"]
        assert line_items["item_precision"] == pytest.approx(2 / 3)
        assert line_items["item_recall"] == 1.0

    def test_no_items_on_both_sides_gives_none_metrics(self, tmp_path):
        predicted = {**FULL_INVOICE, "line_items": []}
        entry = invoice_entry(
            tmp_path, "doc",
            {**FULL_INVOICE, "line_items": []}, predicted,
        )
        line_items = eval_invoices(type("M", (), {"entries": [entry]})())["documents"][0]["line_items"]
        assert line_items["item_precision"] is None
        assert line_items["item_recall"] is None
        assert line_items["item_f1"] is None


class TestTableEvaluation:
    @staticmethod
    def truth(rows, columns, cells):
        return {"rows": rows, "columns": columns, "cells": cells}

    @staticmethod
    def prediction(tables):
        return {"source_image": "x", "tables": tables}

    @staticmethod
    def pred_table(rows, columns, cells, index=0):
        return {
            "table_id": f"table_{index}", "rows": rows, "columns": columns,
            "cells": [
                {"row_index": r, "column_index": c, "text": cells[r][c],
                 "bounding_box": [[0, 0], [1, 0], [1, 1], [0, 1]],
                 "source_ocr_indices": [], "confidence": 0.9}
                for r in range(rows) for c in range(columns)
            ],
            "warnings": [],
        }

    def eval_one(self, tmp_path, doc_id, expected_tables, predicted_tables):
        gt = write_json(tmp_path / "gt" / f"{doc_id}.json",
                        {"id": doc_id, "tables": expected_tables})
        pred = write_json(tmp_path / "pred" / f"{doc_id}.json",
                          self.prediction(predicted_tables))
        return eval_tables(
            type("M", (), {"entries": [ManifestEntry(doc_id, pred, gt)]})()
        )

    def test_perfect_table(self, tmp_path):
        cells = [["Item", "Qty"], ["Coffee", ""]]
        summary = self.eval_one(tmp_path, "doc", [self.truth(2, 2, cells)],
                                [self.pred_table(2, 2, cells)])
        comparison = summary["documents"][0]["comparisons"][0]
        assert comparison["structure_ok"] is True
        assert comparison["cell_exact_agreement"] == 1.0
        assert comparison["empty_cell_preservation"] == 1.0
        assert summary["aggregate"]["structure_ok_documents"] == 1

    def test_shape_mismatch(self, tmp_path):
        cells = [["A", "B"], ["C", "D"]]
        summary = self.eval_one(tmp_path, "doc", [self.truth(2, 2, cells)],
                                [self.pred_table(1, 2, [cells[0]])])
        comparison = summary["documents"][0]["comparisons"][0]
        assert comparison["structure_ok"] is False
        assert summary["aggregate"]["structure_ok_documents"] == 0
        assert comparison["missing_cells"] == 2

    def test_incorrect_and_empty_cells(self, tmp_path):
        cells = [["Item", "Qty"], ["Coffee", ""]]
        predicted = [["Item", "QTY"], ["", ""]]
        summary = self.eval_one(tmp_path, "doc", [self.truth(2, 2, cells)],
                                [self.pred_table(2, 2, predicted)])
        comparison = summary["documents"][0]["comparisons"][0]
        assert comparison["cells_matched"] == 3  # "Item", "QTY"~"Qty", empty cell
        assert comparison["incorrect_cells"] == 0
        assert comparison["missing_cells"] == 1  # "Coffee" predicted empty
        assert comparison["empty_cell_preservation"] == 1.0

    def test_missed_table_never_scores_perfect(self, tmp_path):
        cells = [["A", "B"], ["C", "D"]]
        expected = [self.truth(2, 2, cells), self.truth(2, 2, cells)]
        summary = self.eval_one(tmp_path, "doc", expected,
                                [self.pred_table(2, 2, cells)])
        doc = summary["documents"][0]
        assert doc["tables_missed"] == 1
        # only one table's cells can match; the missed table counts as unmatched
        assert summary["aggregate"]["cell_exact_agreement"] == pytest.approx(0.5)
        assert summary["aggregate"]["structure_ok_documents"] == 0

    def test_extra_table_counted(self, tmp_path):
        cells = [["A", "B"], ["C", "D"]]
        summary = self.eval_one(tmp_path, "doc", [self.truth(2, 2, cells)],
                                [self.pred_table(2, 2, cells),
                                 self.pred_table(2, 2, cells, index=1)])
        doc = summary["documents"][0]
        assert doc["tables_extra"] == 1
        assert summary["aggregate"]["structure_ok_documents"] == 0

    def test_normalization_casefold_and_whitespace(self, tmp_path):
        cells = [["Red  Delicious Apple", "12"]]
        predicted = [["red delicious apple", "12"]]
        summary = self.eval_one(tmp_path, "doc", [self.truth(1, 2, cells)],
                                [self.pred_table(1, 2, predicted)])
        comparison = summary["documents"][0]["comparisons"][0]
        assert comparison["cells_matched"] == 2
