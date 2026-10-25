"""OCR-to-cell assignment tests (pure geometry, no OCR model)."""

from documind.tables.assign import assign_ocr_to_cells
from documind.tables.geometry import GridGeometry


def make_grid():
    return GridGeometry(
        row_edges=[0, 10, 20],
        col_edges=[0, 10, 20],
    )


def item(text, cx, cy, confidence=0.95, index=None):
    box = [[cx - 5, cy - 3], [cx + 5, cy - 3], [cx + 5, cy + 3], [cx - 5, cy + 3]]
    payload = {"text": text, "box": box}
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


class TestAssignment:
    def test_center_point_assignment(self):
        items = [item("A", 5, 5), item("B", 15, 5), item("C", 5, 15), item("D", 15, 15)]
        cells, warnings = assign_ocr_to_cells(make_grid(), items)
        assert warnings == []
        assert [c.text for c in cells] == ["A", "B", "C", "D"]
        assert cells[0].source_ocr_indices == [0]
        assert cells[3].source_ocr_indices == [3]

    def test_multiple_tokens_in_one_cell_join_in_reading_order(self):
        # Cell (0, 1) spans x in [10, 20), y in [0, 10); both centers fall
        # inside it and y-then-x order puts "Hello" before "World".
        items = [item("Hello", 12, 4), item("World", 16, 6)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        assert cells[1].text == "Hello World"
        assert cells[1].source_ocr_indices == [0, 1]

    def test_empty_cells_stay_empty(self):
        items = [item("A", 5, 5)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        last = cells[3]
        assert last.text == ""
        assert last.source_ocr_indices == []
        assert last.confidence is None

    def test_confidence_is_mean_of_assigned_regions(self):
        items = [item("x", 6, 6, confidence=0.9), item("y", 8, 7, confidence=0.7)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        assert abs(cells[0].confidence - 0.8) < 1e-9

    def test_unassigned_regions_reported_not_dropped_silently(self):
        items = [item("A", 5, 5), item("OUTSIDE", 100, 100)]
        cells, warnings = assign_ocr_to_cells(make_grid(), items)
        assert cells[0].text == "A"
        assert any("1 OCR region(s) outside" in w for w in warnings)
        assert all("OUTSIDE" not in c.text for c in cells)

    def test_region_without_box_is_unassigned(self):
        items = [{"text": "NoBox", "box": []}]
        cells, warnings = assign_ocr_to_cells(make_grid(), items)
        assert all(c.text == "" for c in cells)
        assert warnings

    def test_blank_text_is_skipped(self):
        items = [{"text": "   ", "box": [[0, 0], [4, 0], [4, 4], [0, 4]]}]
        cells, warnings = assign_ocr_to_cells(make_grid(), items)
        assert all(c.text == "" for c in cells)
        assert warnings == []

    def test_center_fallback_to_largest_overlap(self):
        # Center just outside the grid edge (y = -1) but the box overlaps
        # the first row -> assigned by intersection area, not dropped.
        payload = {
            "text": "EDGE",
            "box": [[2, -3], [8, -3], [8, 3], [2, 3]],
        }
        cells, warnings = assign_ocr_to_cells(make_grid(), [payload])
        assert cells[0].text == "EDGE"
        assert warnings == []
