"""Unit tests for OCR input validation."""

import pytest

from documind.ocr.validation import ValidationError, validate_image


class TestValidateImage:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValidationError, match="not found"):
            validate_image(tmp_path / "does_not_exist.png")

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ValidationError, match="not a file"):
            validate_image(tmp_path)

    def test_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "document.gif"
        path.write_bytes(b"some bytes")
        with pytest.raises(ValidationError, match="Unsupported image format"):
            validate_image(path)

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.png"
        path.touch()
        with pytest.raises(ValidationError, match="empty"):
            validate_image(path)

    def test_oversized_file_raises(self, sample_png):
        with pytest.raises(ValidationError, match="too large"):
            validate_image(sample_png, max_size_bytes=3)

    def test_valid_image_passes(self, sample_png):
        result = validate_image(sample_png)
        assert result.path == sample_png
        assert result.size_bytes > 0

    def test_extension_check_is_case_insensitive(self, tmp_path):
        path = tmp_path / "photo.JPG"
        path.write_bytes(b"x")
        result = validate_image(path)  # .JPG is accepted like .jpg
        assert result.size_bytes == 1
