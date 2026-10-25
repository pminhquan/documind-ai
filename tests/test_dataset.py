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
