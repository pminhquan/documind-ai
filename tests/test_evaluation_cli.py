"""Manifest validation, CLI behavior, and report generation tests."""

import json
from pathlib import Path

import pytest

from documind.evaluation.cli import main
from documind.evaluation.manifest import ManifestError, load_manifest
from documind.evaluation.report import render_markdown


class TestManifest:
    def write(self, tmp_path, data, name="manifest.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_manifest_loads_and_resolves_relative_paths(self, tmp_path):
        (tmp_path / "pred").mkdir()
        path = self.write(tmp_path, {
            "task": "ocr",
            "documents": [{"id": "d1", "prediction": "pred/d1.json",
                           "ground_truth": "gt/d1.json"}],
        })
        manifest = load_manifest(path)
        assert manifest.task == "ocr"
        assert manifest.entries[0].prediction == tmp_path / "pred" / "d1.json"
        assert manifest.entries[0].ground_truth == tmp_path / "gt" / "d1.json"

    def test_unknown_task_rejected(self, tmp_path):
        path = self.write(tmp_path, {"task": "magic", "documents": []})
        with pytest.raises(ManifestError, match="task"):
            load_manifest(path)

    def test_empty_documents_rejected(self, tmp_path):
        path = self.write(tmp_path, {"task": "ocr", "documents": []})
        with pytest.raises(ManifestError, match="non-empty"):
            load_manifest(path)

    def test_missing_entry_fields_rejected(self, tmp_path):
        path = self.write(tmp_path, {
            "task": "ocr",
            "documents": [{"id": "d1", "prediction": "a.json"}],
        })
        with pytest.raises(ManifestError, match="ground_truth"):
            load_manifest(path)

    def test_duplicate_ids_rejected(self, tmp_path):
        path = self.write(tmp_path, {
            "task": "ocr",
            "documents": [
                {"id": "d1", "prediction": "a", "ground_truth": "b"},
                {"id": "d1", "prediction": "c", "ground_truth": "d"},
            ],
        })
        with pytest.raises(ManifestError, match="Duplicate"):
            load_manifest(path)

    def test_malformed_json_rejected(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ManifestError, match="Malformed"):
            load_manifest(path)


def make_ocr_eval_files(tmp_path: Path, doc_id: str, reference: str, full_text: str):
    gt = tmp_path / "gt" / f"{doc_id}.json"
    gt.parent.mkdir(parents=True, exist_ok=True)
    gt.write_text(json.dumps({"id": doc_id, "reference_text": reference}),
                  encoding="utf-8")
    pred = tmp_path / "pred" / f"{doc_id}.json"
    pred.parent.mkdir(parents=True, exist_ok=True)
    pred.write_text(json.dumps({"full_text": full_text}), encoding="utf-8")
    return {"id": doc_id, "prediction": str(pred), "ground_truth": str(gt)}


class TestEvalCli:
    def test_ocr_happy_path_writes_summary_and_report(self, tmp_path):
        docs = [
            make_ocr_eval_files(tmp_path, "d1", "Total 9.57", "Total 9.57"),
            make_ocr_eval_files(tmp_path, "d2", "kitten", "sitten"),
        ]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": docs}),
                            encoding="utf-8")
        output = tmp_path / "out"
        code = main(["--task", "ocr", "--manifest", str(manifest),
                     "--output", str(output)])
        assert code == 0
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        assert summary["task"] == "ocr"
        # "total 9.57" (10 chars) + "kitten" (6 chars) = 16 reference chars
        assert summary["aggregate"]["cer_total_reference_chars"] == 16
        report = (output / "report.md").read_text(encoding="utf-8")
        assert "# Evaluation report — task: ocr" in report
        assert "## Conventions" in report

    def test_task_defaults_from_manifest(self, tmp_path, capsys):
        docs = [make_ocr_eval_files(tmp_path, "d1", "abc", "abc")]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": docs}),
                            encoding="utf-8")
        assert main(["--manifest", str(manifest), "--output",
                     str(tmp_path / "out")]) == 0
        assert "Task: ocr" in capsys.readouterr().out

    def test_task_contradiction_rejected(self, tmp_path):
        docs = [make_ocr_eval_files(tmp_path, "d1", "abc", "abc")]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": docs}),
                            encoding="utf-8")
        assert main(["--task", "table", "--manifest", str(manifest)]) == 2

    def test_invalid_manifest_returns_2(self, tmp_path, capsys):
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": []}),
                            encoding="utf-8")
        assert main(["--manifest", str(manifest)]) == 2
        assert "Evaluation error" in capsys.readouterr().err

    def test_missing_prediction_file_returns_2(self, tmp_path, capsys):
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({
            "task": "ocr",
            "documents": [{"id": "d1", "prediction": "nope.json",
                           "ground_truth": "also_nope.json"}],
        }), encoding="utf-8")
        assert main(["--manifest", str(manifest)]) == 2


class TestProvenance:
    def test_manifest_defaults_to_unknown(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({
            "task": "ocr",
            "documents": [make_ocr_eval_files(tmp_path, "d1", "abc", "abc")],
        }), encoding="utf-8")
        assert load_manifest(path).provenance == "unknown"

    def test_declared_provenance_is_kept(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({
            "task": "ocr",
            "provenance": "synthetic",
            "documents": [make_ocr_eval_files(tmp_path, "d1", "abc", "abc")],
        }), encoding="utf-8")
        assert load_manifest(path).provenance == "synthetic"

    def test_invalid_provenance_rejected(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({
            "task": "ocr",
            "provenance": "definitely-real-trust-me",
            "documents": [make_ocr_eval_files(tmp_path, "d1", "abc", "abc")],
        }), encoding="utf-8")
        with pytest.raises(ManifestError, match="provenance"):
            load_manifest(path)

    def test_summary_and_report_carry_provenance(self, tmp_path):
        docs = [make_ocr_eval_files(tmp_path, "d1", "abc", "abd")]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({
            "task": "ocr", "provenance": "synthetic", "documents": docs,
        }), encoding="utf-8")
        output = tmp_path / "out"
        assert main(["--manifest", str(manifest), "--output", str(output)]) == 0
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        assert summary["dataset"]["provenance"] == "synthetic"
        report = (output / "report.md").read_text(encoding="utf-8")
        assert "Dataset provenance: synthetic" in report

    def test_unknown_provenance_caveat_in_report(self, tmp_path):
        docs = [make_ocr_eval_files(tmp_path, "d1", "abc", "abd")]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": docs}),
                            encoding="utf-8")
        output = tmp_path / "out"
        main(["--manifest", str(manifest), "--output", str(output)])
        report = (output / "report.md").read_text(encoding="utf-8")
        assert "Dataset provenance: unknown" in report
        assert "do not treat these numbers as real-world accuracy" in report


class TestOperationCounts:
    """Regression: error analysis needs reproducible operation-type
    statistics, not just the first five examples."""

    def test_summary_counts_operations(self, tmp_path):
        docs = [make_ocr_eval_files(tmp_path, "d1", "kitten", "sitten")]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": docs}),
                            encoding="utf-8")
        output = tmp_path / "out"
        main(["--manifest", str(manifest), "--output", str(output)])
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        doc = summary["documents"][0]
        # kitten -> sitten: single substitution k -> s
        assert doc["operation_counts"] == {"substitute": 1, "insert": 0, "delete": 0}
        assert sum(doc["operation_counts"].values()) == doc["cer_edits"]
        aggregate = summary["aggregate"]
        assert aggregate["substitutions"] == 1
        assert aggregate["insertions"] == 0
        assert aggregate["deletions"] == 0

    def test_report_shows_operation_mix(self, tmp_path):
        docs = [make_ocr_eval_files(tmp_path, "d1", "kitten", "sitten")]
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"task": "ocr", "documents": docs}),
                            encoding="utf-8")
        output = tmp_path / "out"
        main(["--manifest", str(manifest), "--output", str(output)])
        report = (output / "report.md").read_text(encoding="utf-8")
        assert "Edit mix" in report
        assert "substitutions: 1" in report


class TestWorstDocumentsReport:
    """Error-analysis section: worst documents and problem fields."""

    @staticmethod
    def _summary_with_two_docs():
        from documind.evaluation.manifest import ManifestEntry
        from documind.evaluation.ocr_eval import evaluate_manifest

        entries = []
        for doc_id, reference, hypothesis in (
            ("good", "TOTAL 9.57", "TOTAL 9.57"),
            ("bad", "TOTAL 9.57", "T0TAL 9,57"),
        ):
            gt = Path(doc_id + ".gt.json")
            pred = Path(doc_id + ".pred.json")
            gt.write_text(json.dumps({"id": doc_id, "reference_text": reference}),
                          encoding="utf-8")
            pred.write_text(json.dumps({"full_text": hypothesis}),
                            encoding="utf-8")
            entries.append(ManifestEntry(doc_id, pred, gt))
        return evaluate_manifest(type("M", (), {"entries": entries})())

    def test_ocr_report_names_worst_document_first(self, tmp_path, monkeypatch):
        from documind.evaluation.report import render_markdown

        monkeypatch.chdir(tmp_path)
        report = render_markdown(self._summary_with_two_docs())
        worst_section = report.split("Worst-performing documents")[1]
        assert worst_section.index("bad") < worst_section.index("good")

    def test_invoice_report_lists_problem_fields(self, tmp_path):
        from documind.evaluation.invoice_eval import evaluate_manifest
        from documind.evaluation.report import render_markdown

        full_invoice = {
            "supplier": "ACME", "invoice_number": "1", "invoice_date": "2026-01-01",
            "currency": "USD", "subtotal": "10.00", "tax": "1.00",
            "discount": None, "total": "11.00", "payment_amount": None,
            "change_amount": None, "line_items": [],
        }
        predicted = {**full_invoice, "total": "99.99", "tax": None}
        gt = tmp_path / "gt.json"
        gt.write_text(json.dumps({"id": "d", "invoice": full_invoice}),
                      encoding="utf-8")
        pred = tmp_path / "pred.json"
        pred.write_text(json.dumps({"invoice": predicted}), encoding="utf-8")
        summary = evaluate_manifest(
            type("M", (), {"entries": [__import__(
                "documind.evaluation.manifest", fromlist=["ManifestEntry"]
            ).ManifestEntry("d", pred, gt)]})()
        )
        report = render_markdown(summary)
        assert "Most problematic fields" in report
        assert "**total**: issues in 1 document(s)" in report
        assert "**tax**: issues in 1 document(s)" in report
        assert "Worst-performing documents (lowest field accuracy)" in report


class TestReport:
    @staticmethod
    def _invoice_entry(tmp_path: Path, doc_id: str, expected_invoice, predicted_invoice):
        # Self-contained copy of the tasks-test helper: test modules are
        # not importable as a package in CI.
        gt = tmp_path / "gt" / f"{doc_id}.json"
        gt.parent.mkdir(parents=True, exist_ok=True)
        gt.write_text(json.dumps({"id": doc_id, "invoice": expected_invoice}),
                      encoding="utf-8")
        pred = tmp_path / "pred" / f"{doc_id}.json"
        pred.parent.mkdir(parents=True, exist_ok=True)
        pred.write_text(json.dumps({"source": "x", "invoice": predicted_invoice}),
                        encoding="utf-8")
        from documind.evaluation.manifest import ManifestEntry

        return ManifestEntry(id=doc_id, prediction=pred, ground_truth=gt)

    def test_invoice_report_lists_field_issues(self, tmp_path):
        from documind.evaluation.invoice_eval import evaluate_manifest

        full_invoice = {
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
                {"description": "SOAP", "quantity": "2", "unit_price": "2.50",
                 "line_total": "5.00"},
            ],
        }
        predicted = {**full_invoice, "total": None, "tax": "9.99"}
        entry = self._invoice_entry(tmp_path, "doc", full_invoice, predicted)
        summary = evaluate_manifest(type("M", (), {"entries": [entry]})())
        report = render_markdown(summary)
        assert "total: missing" in report
        assert "tax: incorrect" in report
        assert "Micro field accuracy" in report

    def test_table_report_mentions_aggregates(self, tmp_path):
        from documind.evaluation.manifest import ManifestEntry
        from documind.evaluation.table_eval import evaluate_manifest

        truth = {"rows": 1, "columns": 1, "cells": [["A"]]}
        prediction = {"tables": [{"table_id": "table_0", "rows": 1, "columns": 1,
                                  "cells": [{"row_index": 0, "column_index": 0,
                                             "text": "A"}]}]}
        gt = tmp_path / "gt.json"
        gt.write_text(json.dumps({"id": "d", "tables": [truth]}), encoding="utf-8")
        pred = tmp_path / "pred.json"
        pred.write_text(json.dumps({"tables": prediction["tables"]}), encoding="utf-8")
        summary = evaluate_manifest(
            type("M", (), {"entries": [ManifestEntry("d", pred, gt)]})()
        )
        report = render_markdown(summary)
        assert "cell exact agreement 1.0000" in report
        assert "tables expected 1" in report
