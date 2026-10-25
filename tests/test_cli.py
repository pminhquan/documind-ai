"""CLI tests: help, error handling, and a mocked end-to-end run."""

import json

import pytest

from documind import cli


class TestCliHelp:
    def test_help_exits_zero_and_prints_usage(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower()
        assert "documind-ocr" in captured.out


class TestCliErrors:
    def test_missing_input_returns_error_code(self, capsys):
        exit_code = cli.main(["definitely_missing_input.png"])
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_undecodable_image_returns_error_code(self, tmp_path, capsys):
        fake = tmp_path / "fake.png"
        fake.write_bytes(b"this is not really a png image")
        exit_code = cli.main([str(fake), "-o", str(tmp_path / "out.json")])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "OCR error" in captured.err


class TestCliMockedInference:
    @pytest.fixture
    def fake_engine(self, monkeypatch):
        """Replace the PaddleOCR engine with a canned response."""

        class FakeEngine:
            def __init__(self, lang="en"):
                self.lang = lang

            def predict(self, image_path):
                return [
                    {
                        "rec_texts": ["TOTAL 8.70"],
                        "rec_scores": [0.97],
                        "rec_polys": [[[1, 2], [30, 2], [30, 20], [1, 20]]],
                    }
                ]

        monkeypatch.setattr(cli, "PaddleOcrEngine", FakeEngine)
        return FakeEngine

    def test_run_writes_normalized_json(self, sample_png, tmp_path, fake_engine):
        output = tmp_path / "result.json"
        exit_code = cli.main([str(sample_png), "-o", str(output)])
        assert exit_code == 0

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["items"][0]["text"] == "TOTAL 8.70"
        assert data["items"][0]["confidence"] == pytest.approx(0.97)
        assert data["items"][0]["box"] == [[1, 2], [30, 2], [30, 20], [1, 20]]
        assert data["full_text"] == "TOTAL 8.70"
        assert data["source"] == str(sample_png)

    def test_run_reports_item_count(self, sample_png, tmp_path, fake_engine, capsys):
        exit_code = cli.main(
            [str(sample_png), "-o", str(tmp_path / "result.json")]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Recognized 1 text region(s)" in captured.out

    def test_grayscale_image_is_converted(
        self, sample_png, tmp_path, fake_engine, monkeypatch
    ):
        """Non-RGB inputs go through preprocessing and still run."""
        from PIL import Image

        gray = tmp_path / "gray.png"
        Image.new("L", (16, 16), color=128).save(gray, format="PNG")

        seen_paths = []
        original_prepare = cli.prepare_image

        def spying_prepare(path):
            cm = original_prepare(path)
            with cm as prepared:
                seen_paths.append(prepared)
                yield prepared

        import contextlib

        monkeypatch.setattr(
            cli, "prepare_image", contextlib.contextmanager(spying_prepare)
        )

        output = tmp_path / "result.json"
        exit_code = cli.main([str(gray), "-o", str(output)])
        assert exit_code == 0
        assert seen_paths and seen_paths[0].suffix == ".png"
