"""Dataset onboarding/validation tests (pure logic, no model)."""

import json
from pathlib import Path

import pytest
from PIL import Image

from documind.dataset import (
    DatasetError,
    add_document,
    annotated_document_ids,
    build_task_manifest,
    dataset_root,
    init_dataset,
    validate_dataset,
    write_task_manifest,
)
from documind.dataset_cli import main


@pytest.fixture
def root(tmp_path):
    return dataset_root(tmp_path / "real")


@pytest.fixture
def initialized_root(root):
    init_dataset(root)
    return root


def make_image(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    Image.new("RGB", (20, 20), color="white").save(path)
    return path


class TestInit:
    def test_creates_layout_and_readme(self, root):
        init_dataset(root)
        for name in ("raw", "anonymized", "ground_truth", "predictions", "reports"):
            assert (root / name).is_dir()
        assert "Provenance: **real**" in (root / "README.md").read_text(encoding="utf-8")

    def test_second_init_refuses_to_clobber(self, initialized_root):
        (initialized_root / "README.md").write_text("owner notes", encoding="utf-8")
        with pytest.raises(DatasetError, match="already initialized"):
            init_dataset(initialized_root)
        assert (initialized_root / "README.md").read_text(encoding="utf-8") == "owner notes"


class TestAdd:
    def test_requires_explicit_anonymization_confirmation(self, initialized_root, tmp_path):
        image = make_image(tmp_path / "raw", "receipt-001.jpg")
        with pytest.raises(DatasetError, match="confirm-anonymized"):
            add_document(image, "receipt-001", root=initialized_root)
        assert list((initialized_root / "anonymized").iterdir()) == []

    def test_rejects_unsafe_ids(self, initialized_root, tmp_path):
        image = make_image(tmp_path / "raw", "x.jpg")
        with pytest.raises(DatasetError, match="invalid document id"):
            add_document(image, "../escape", root=initialized_root,
                         confirm_anonymized=True)

    def test_copies_and_registers(self, initialized_root, tmp_path):
        image = make_image(tmp_path / "raw", "receipt-001.JPG")
        target = add_document(image, "receipt-001", root=initialized_root,
                              confirm_anonymized=True)
        assert target == initialized_root / "anonymized" / "receipt-001.jpg"
        assert target.exists()

    def test_duplicate_id_rejected(self, initialized_root, tmp_path):
        image = make_image(tmp_path / "raw", "receipt-001.jpg")
        add_document(image, "receipt-001", root=initialized_root,
                     confirm_anonymized=True)
        with pytest.raises(DatasetError, match="already exists"):
            add_document(image, "receipt-001", root=initialized_root,
                         confirm_anonymized=True)


class TestValidate:
    def test_fresh_dataset_is_valid(self, initialized_root):
        ok, lines = validate_dataset(initialized_root)
        assert ok is True
        assert any("documents in anonymized/: 0" in line for line in lines)

    def test_uninitialized_dataset_fails_with_hint(self, tmp_path):
        ok, lines = validate_dataset(tmp_path / "missing")
        assert ok is False
        assert any("documind-dataset init" in line for line in lines)

    def _add_document(self, root, doc_id="receipt-001"):
        raw = root.parent / "raw-src"
        image = make_image(raw, f"{doc_id}.png")
        return add_document(image, doc_id, root=root, confirm_anonymized=True)

    def test_placeholder_annotation_is_an_error(self, initialized_root):
        self._add_document(initialized_root)
        gt = initialized_root / "ground_truth" / "receipt-001.ocr.json"
        gt.write_text(json.dumps({"id": "receipt-001",
                                  "reference_text": "<full text transcription>"}),
                      encoding="utf-8")
        ok, lines = validate_dataset(initialized_root)
        assert ok is False
        assert any("unresolved placeholder" in line for line in lines)

    def test_invoice_missing_keys_are_an_error(self, initialized_root):
        self._add_document(initialized_root)
        gt = initialized_root / "ground_truth" / "receipt-001.invoice.json"
        gt.write_text(json.dumps({"id": "receipt-001",
                                  "invoice": {"supplier": "X", "total": "1.00"}}),
                      encoding="utf-8")
        ok, lines = validate_dataset(initialized_root)
        assert ok is False
        assert any("missing keys" in line for line in lines)

    def test_table_matrix_mismatch_is_an_error(self, initialized_root):
        self._add_document(initialized_root)
        gt = initialized_root / "ground_truth" / "receipt-001.table.json"
        gt.write_text(json.dumps({"id": "receipt-001", "tables": [
            {"rows": 2, "columns": 2, "cells": [["A", "B"]]}
        ]}), encoding="utf-8")
        ok, lines = validate_dataset(initialized_root)
        assert ok is False
        assert any("cells matrix must be 2x2" in line for line in lines)

    def test_valid_annotations_pass(self, initialized_root):
        self._add_document(initialized_root)
        gt_dir = initialized_root / "ground_truth"
        (gt_dir / "receipt-001.ocr.json").write_text(
            json.dumps({"id": "receipt-001", "reference_text": "TOTAL 9.57"}),
            encoding="utf-8")
        (gt_dir / "receipt-001.invoice.json").write_text(json.dumps({
            "id": "receipt-001",
            "invoice": {"supplier": None, "invoice_number": None,
                        "invoice_date": None, "currency": None, "subtotal": None,
                        "tax": None, "discount": None, "total": "9.57",
                        "payment_amount": None, "change_amount": None,
                        "line_items": []},
        }), encoding="utf-8")
        ok, lines = validate_dataset(initialized_root)
        assert ok is True
        assert any("ocr: 1/1 annotated" in line for line in lines)


class TestManifestBuilding:
    def test_only_annotated_documents_included(self, initialized_root):
        gt_dir = initialized_root / "ground_truth"
        gt_dir.mkdir(parents=True, exist_ok=True)
        gt_dir / "doc-a.ocr.json"
        # two images, only one annotated
        make_image(initialized_root / "anonymized", "doc-a.png")
        make_image(initialized_root / "anonymized", "doc-b.png")
        (gt_dir / "doc-a.ocr.json").write_text(
            json.dumps({"id": "doc-a", "reference_text": "x"}), encoding="utf-8")

        manifest = build_task_manifest(initialized_root, "ocr")
        assert manifest["provenance"] == "real"
        assert manifest["documents"] == [{
            "id": "doc-a",
            "prediction": "predictions/doc-a.ocr.json",
            "ground_truth": "ground_truth/doc-a.ocr.json",
        }]
        assert annotated_document_ids(initialized_root, "invoice") == []

        path = write_task_manifest(initialized_root, "ocr")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["documents"][0]["id"] == "doc-a"


class TestDatasetCli:
    def test_init_add_validate_happy_path(self, tmp_path, capsys):
        raw_image = make_image(tmp_path / "raw", "receipt-001.png")
        root = tmp_path / "real"
        assert main(["init", "--root", str(root)]) == 0
        assert main(["add", str(raw_image), "--id", "receipt-001",
                     "--root", str(root)]) == 2  # missing confirmation
        captured = capsys.readouterr()
        assert "confirm-anonymized" in captured.err
        assert main(["add", str(raw_image), "--id", "receipt-001",
                     "--root", str(root), "--confirm-anonymized"]) == 0
        assert main(["validate", "--root", str(root)]) == 0

    def test_validate_with_errors_returns_1(self, tmp_path):
        root = tmp_path / "real"
        main(["init", "--root", str(root)])
        make_image(root / "anonymized", "doc.png")
        (root / "ground_truth" / "doc.ocr.json").write_text(
            "{not json", encoding="utf-8")
        assert main(["validate", "--root", str(root)]) == 1

    def test_predict_without_annotations_is_a_noop(self, tmp_path, capsys):
        root = tmp_path / "real"
        main(["init", "--root", str(root)])
        assert main(["predict", "--task", "ocr", "--root", str(root)]) == 0
        assert "nothing to predict" in capsys.readouterr().out

    def test_unknown_task_rejected_by_argparse(self, tmp_path):
        root = tmp_path / "real"
        main(["init", "--root", str(root)])
        with pytest.raises(SystemExit) as exc_info:
            main(["predict", "--task", "magic", "--root", str(root)])
        assert exc_info.value.code == 2


class TestIntegrationWorkflow:
    """Finding 1: validate_dataset imported load_manifest from a
    nonexistent module, so a VALID generated manifest was reported
    invalid. Full chain: init -> add -> GT -> predict (mocked OCR) ->
    manifest -> validate -> eval."""

    def test_full_workflow_with_mocked_ocr(self, tmp_path, monkeypatch):
        root = tmp_path / "real"
        assert main(["init", "--root", str(root)]) == 0
        image = make_image(tmp_path, "receipt-001.png")
        assert main(["add", str(image), "--id", "receipt-001",
                     "--root", str(root), "--confirm-anonymized"]) == 0
        gt = root / "ground_truth" / "receipt-001.ocr.json"
        gt.write_text(json.dumps({"id": "receipt-001",
                                  "reference_text": "TOTAL 9.57"}),
                      encoding="utf-8")

        calls = []

        def fake_ocr_main(argv):
            calls.append(argv)
            output = Path(argv[argv.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "engine": "mock", "full_text": "TOTAL 9.57",
                "items": [{"text": "TOTAL 9.57", "confidence": 0.99,
                           "box": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
            }), encoding="utf-8")
            return 0

        monkeypatch.setattr("documind.cli.main", fake_ocr_main)
        assert main(["predict", "--task", "ocr", "--root", str(root)]) == 0
        assert len(calls) == 1

        manifest_path = root / "manifest-ocr.json"
        assert manifest_path.exists()
        ok, lines = validate_dataset(root)
        assert ok is True, lines
        assert not any("invalid manifest" in line for line in lines)
        assert any("ready to evaluate: ocr" in line for line in lines)

        from documind.evaluation.cli import main as eval_main
        from documind.evaluation.manifest import load_manifest

        manifest = load_manifest(manifest_path)
        assert manifest.provenance == "real"
        output = tmp_path / "eval-out"
        assert eval_main(["--task", "ocr", "--manifest", str(manifest_path),
                          "--output", str(output)]) == 0
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        assert summary["aggregate"]["cer"] == 0.0

    def test_invalid_manifest_fails_with_clear_error(self, tmp_path):
        root = tmp_path / "real"
        main(["init", "--root", str(root)])
        (root / "manifest-ocr.json").write_text(
            json.dumps({"task": "bogus", "documents": []}), encoding="utf-8")
        ok, lines = validate_dataset(root)
        assert ok is False
        assert any("invalid manifest" in line and "task" in line for line in lines)
        assert main(["validate", "--root", str(root)]) == 1


class TestDuplicateDocumentIds:
    """Finding 2: uniqueness was filename-based, so receipt-001.png did
    not block receipt-001.jpg."""

    def test_duplicate_id_across_extensions_rejected(self, initialized_root, tmp_path):
        first = make_image(tmp_path / "raw", "receipt-001.png")
        add_document(first, "receipt-001", root=initialized_root,
                     confirm_anonymized=True)
        original_bytes = (initialized_root / "anonymized" / "receipt-001.png"
                          ).read_bytes()

        second = make_image(tmp_path / "raw", "receipt-001.jpg")
        with pytest.raises(DatasetError, match="already"):
            add_document(second, "receipt-001", root=initialized_root,
                         confirm_anonymized=True)
        # existing file preserved untouched
        assert (initialized_root / "anonymized" / "receipt-001.png"
                ).read_bytes() == original_bytes
        assert (initialized_root / "anonymized" / "receipt-001.jpg").exists() is False


class TestStaleOcrPredictions:
    """Finding 3: invoice prediction reused an existing OCR JSON without
    checking it against the current image. OCR is now regenerated for
    every invoice prediction run."""

    @staticmethod
    def _add_invoice_document(root):
        gt = root / "ground_truth" / "receipt-001.invoice.json"
        gt.write_text(json.dumps({
            "id": "receipt-001",
            "invoice": {"supplier": None, "invoice_number": None,
                        "invoice_date": None, "currency": None, "subtotal": None,
                        "tax": None, "discount": None, "total": None,
                        "payment_amount": None, "change_amount": None,
                        "line_items": []},
        }), encoding="utf-8")

    def test_modified_image_cannot_reuse_stale_ocr(self, initialized_root, tmp_path,
                                                   monkeypatch):
        self._add_invoice_document(initialized_root)
        source_image = make_image(tmp_path / "raw", "receipt-001.png")
        add_document(source_image, "receipt-001", root=initialized_root,
                     confirm_anonymized=True)
        image = initialized_root / "anonymized" / "receipt-001.png"
        calls = []

        def fake_ocr_main(argv):
            calls.append(argv)
            output = Path(argv[argv.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "engine": "mock", "full_text": f"content-{len(calls)}",
                "items": [],
            }), encoding="utf-8")
            return 0

        monkeypatch.setattr("documind.cli.main", fake_ocr_main)
        assert main(["predict", "--task", "invoice", "--root",
                     str(initialized_root)]) == 0
        assert len(calls) == 1

        # The source image changes (e.g. re-anonymized with new content).
        image.write_bytes(b"new-image-content-entirely-different")

        assert main(["predict", "--task", "invoice", "--root",
                     str(initialized_root)]) == 0
        assert len(calls) == 2  # regenerated, not silently reused
        ocr_prediction = json.loads(
            (initialized_root / "predictions" / "receipt-001.ocr.json")
            .read_text(encoding="utf-8"))
        assert ocr_prediction["full_text"] == "content-2"


class TestInputValidation:
    """Finding 4: onboarding limits aligned with the OCR pipeline."""

    def test_oversized_image_rejected_at_onboarding(self, initialized_root, tmp_path):
        oversized = tmp_path / "raw" / "big.png"
        oversized.parent.mkdir(parents=True, exist_ok=True)
        oversized.write_bytes(b"\0" * (20 * 1024 * 1024 + 1))  # OCR limit is 20 MB
        with pytest.raises(DatasetError, match="too large"):
            add_document(oversized, "big-doc", root=initialized_root,
                         confirm_anonymized=True)

    def test_size_boundary_exactly_twenty_mb_is_accepted(self, initialized_root, tmp_path):
        exact = tmp_path / "raw" / "exact.png"
        exact.parent.mkdir(parents=True, exist_ok=True)
        exact.write_bytes(b"\0" * (20 * 1024 * 1024))
        target = add_document(exact, "exact-doc", root=initialized_root,
                              confirm_anonymized=True)
        assert target.exists()

    def test_unsupported_extension_rejected(self, initialized_root, tmp_path):
        gif = tmp_path / "raw" / "animation.gif"
        gif.parent.mkdir(parents=True, exist_ok=True)
        gif.write_bytes(b"GIF89a")
        with pytest.raises(DatasetError, match="Unsupported"):
            add_document(gif, "gif-doc", root=initialized_root,
                         confirm_anonymized=True)

    def test_empty_file_rejected(self, initialized_root, tmp_path):
        empty = tmp_path / "raw" / "empty.png"
        empty.parent.mkdir(parents=True, exist_ok=True)
        empty.touch()
        with pytest.raises(DatasetError, match="empty"):
            add_document(empty, "empty-doc", root=initialized_root,
                         confirm_anonymized=True)


class TestMalformedAnnotations:
    """Finding 4: syntactically valid JSON that is not an object must
    produce friendly validation errors, not uncaught exceptions."""

    @pytest.mark.parametrize("malformed", ["[]", '"a string"', "null", "42"])
    def test_non_object_annotations_reported_not_raised(
            self, initialized_root, malformed):
        make_image(initialized_root / "anonymized", "doc.png")
        gt = initialized_root / "ground_truth" / "doc.table.json"
        gt.write_text(malformed, encoding="utf-8")
        ok, lines = validate_dataset(initialized_root)  # must not raise
        assert ok is False
        assert any("JSON object" in line for line in lines)

    def test_non_dict_table_entries_reported(self, initialized_root):
        make_image(initialized_root / "anonymized", "doc.png")
        gt = initialized_root / "ground_truth" / "doc.table.json"
        gt.write_text(json.dumps({"tables": ["not-a-table"]}), encoding="utf-8")
        ok, lines = validate_dataset(initialized_root)
        assert ok is False
        assert any("tables[0]" in line for line in lines)


class TestReadinessReporting:
    def test_ready_after_predict_not_before(self, tmp_path, monkeypatch):
        root = tmp_path / "real"
        main(["init", "--root", str(root)])
        image = make_image(tmp_path, "doc.png")
        main(["add", str(image), "--id", "doc", "--root", str(root),
              "--confirm-anonymized"])
        (root / "ground_truth" / "doc.ocr.json").write_text(
            json.dumps({"id": "doc", "reference_text": "x"}), encoding="utf-8")

        ok, lines = validate_dataset(root)
        assert any("not ready: ocr" in line for line in lines)

        def fake_ocr_main(argv):
            Path(argv[argv.index("-o") + 1]).write_text(
                json.dumps({"full_text": "x", "items": []}))
            return 0

        monkeypatch.setattr("documind.cli.main", fake_ocr_main)
        main(["predict", "--task", "ocr", "--root", str(root)])
        ok, lines = validate_dataset(root)
        assert ok is True
        assert any("ready to evaluate: ocr" in line for line in lines)
