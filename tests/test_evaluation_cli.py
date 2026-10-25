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


class TestReport:
    def test_invoice_report_lists_field_issues(self, tmp_path):
        from tests.test_evaluation_tasks import FULL_INVOICE, invoice_entry
        from documind.evaluation.invoice_eval import evaluate_manifest

        predicted = {**FULL_INVOICE, "total": None, "tax": "9.99"}
        entry = invoice_entry(tmp_path, "doc", FULL_INVOICE, predicted)
        summary = evaluate_manifest(type("M", (), {"entries": [entry]})())
        report = render_markdown(summary)
        assert "total: missing" in report
        assert "tax: incorrect" in report
        assert "Micro field accuracy" in report

    def test_table_report_mentions_aggregates(self, tmp_path):
        from documind.evaluation.table_eval import evaluate_manifest
        from documind.evaluation.manifest import ManifestEntry

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
