"""Unit tests for OCR result normalization (mocked inference output)."""

import json

import pytest

from documind.ocr.results import normalize_result


def _mock_raw():
    """A minimal PaddleOCR 3.x-style single-page result."""
    return {
        "rec_texts": ["MINI MART EXPRESS", "TOTAL 8.70"],
        "rec_scores": [0.9876, 0.9421],
        "rec_polys": [
            [[10, 5], [300, 5], [300, 40], [10, 40]],
            [[12, 400], [200, 400], [200, 430], [12, 430]],
        ],
    }


class TestNormalizeResult:
    def test_items_match_raw_order(self):
        result = normalize_result(_mock_raw(), source="receipt.png")
        assert [item.text for item in result.items] == [
            "MINI MART EXPRESS",
            "TOTAL 8.70",
        ]
        assert result.items[0].confidence == pytest.approx(0.9876)
        assert result.items[1].box == [[12, 400], [200, 400], [200, 430], [12, 430]]

    def test_full_text_joins_lines_with_newlines(self):
        result = normalize_result(_mock_raw())
        assert result.full_text == "MINI MART EXPRESS\nTOTAL 8.70"

    def test_to_dict_is_json_serializable(self):
        result = normalize_result(_mock_raw(), source="receipt.png")
        data = json.loads(json.dumps(result.to_dict()))
        assert data["source"] == "receipt.png"
        assert data["engine"] == "paddleocr"
        assert data["items"][0]["text"] == "MINI MART EXPRESS"
        assert data["full_text"] == "MINI MART EXPRESS\nTOTAL 8.70"

    def test_empty_result_yields_no_items(self):
        result = normalize_result({}, source="blank.png")
        assert result.items == []
        assert result.full_text == ""

    def test_none_result_yields_no_items(self):
        result = normalize_result(None, source="blank.png")
        assert result.items == []

    def test_missing_score_defaults_to_zero(self):
        raw = {
            "rec_texts": ["ONLY TEXT"],
            "rec_scores": [],
            "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
        }
        result = normalize_result(raw)
        assert result.items[0].confidence == 0.0

    def test_fallback_polygon_key_dt_polys(self):
        raw = {
            "rec_texts": ["TEXT"],
            "rec_scores": [0.5],
            "dt_polys": [[[1, 2], [3, 4], [5, 6], [7, 8]]],
        }
        result = normalize_result(raw)
        assert result.items[0].box == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]
