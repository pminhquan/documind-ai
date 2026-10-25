"""Tests for the documind-extract CLI."""

import json
from pathlib import Path

import pytest

from documind import extract_cli

FIXTURES = Path(__file__).parent / "fixtures" / "ocr"


class TestExtractCliHelp:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            extract_cli.main(["--help"])
        assert exc_info.value.code == 0
        assert "documind-extract" in capsys.readouterr().out


class TestExtractCliErrors:
    def test_missing_input_returns_2(self, capsys):
        code = extract_cli.main(["no_such_ocr.json"])
        assert code == 2
        assert "not found" in capsys.readouterr().err

    def test_unsupported_extension_returns_2(self, tmp_path, capsys):
        path = tmp_path / "image.png"
        path.write_bytes(b"x")
        code = extract_cli.main([str(path)])
        assert code == 2
        assert "Unsupported file format" in capsys.readouterr().err

    def test_malformed_json_returns_2(self, tmp_path, capsys):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        code = extract_cli.main([str(path)])
        assert code == 2
        assert "Malformed JSON" in capsys.readouterr().err

    def test_missing_items_array_returns_2(self, tmp_path, capsys):
        path = tmp_path / "nonsense.json"
        path.write_text('{"pages": 1}', encoding="utf-8")
        code = extract_cli.main([str(path)])
        assert code == 2
        assert "items" in capsys.readouterr().err


class TestExtractCliHappyPath:
    def test_writes_invoice_json(self, tmp_path):
        output = tmp_path / "invoice.json"
        code = extract_cli.main(
            [str(FIXTURES / "normal_receipt.json"), "-o", str(output)]
        )
        assert code == 0
        data = json.loads(output.read_text(encoding="utf-8"))
        invoice = data["invoice"]
        assert invoice["supplier"] == "MINI MART EXPRESS"
        assert invoice["total"] == "9.57"
        assert invoice["validation_status"] == "ok"
        assert len(invoice["line_items"]) == 3
        assert "provenance" in data

    def test_default_output_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        code = extract_cli.main([str(FIXTURES / "normal_receipt.json")])
        assert code == 0
        default = tmp_path / "outputs" / "normal_receipt.invoice.json"
        assert default.exists()

    def test_summary_mentions_status(self, tmp_path, capsys):
        output = tmp_path / "invoice.json"
        extract_cli.main(
            [str(FIXTURES / "normal_receipt.json"), "-o", str(output)]
        )
        captured = capsys.readouterr()
        assert "status=ok" in captured.out
        assert "line_items=3" in captured.out
