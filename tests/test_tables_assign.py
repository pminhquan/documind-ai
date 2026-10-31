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


class TestReadingOrder:
    """Regression: the old sort key was (center_x, center_y), which put a
    bottom-left token before a top-right one across line boundaries.
    Reading order must be top-to-bottom, then left-to-right within a line
    (line tolerance: 50% of the smaller box height)."""

    def test_top_line_before_bottom_despite_x_order(self):
        # Cell (0, 1) spans x in [10, 20), y in [0, 10); both boxes are
        # 6 px tall -> line tolerance 3 px. "Total" sits top-right,
        # "13.50" bottom-left; the old x-first sort reversed them.
        items = [item("Total", 17, 3), item("13.50", 11, 8)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        assert cells[1].text == "Total 13.50"
        assert cells[1].source_ocr_indices == [0, 1]

    def test_small_jitter_within_one_line_keeps_x_order(self):
        # y centers 4 and 5 (diff 1 <= tolerance 3): same visual line.
        items = [item("World", 16, 5), item("Hello", 12, 4)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        assert cells[1].text == "Hello World"
        assert cells[1].source_ocr_indices == [1, 0]

    def test_three_tokens_two_lines_ordering(self):
        items = [item("C", 18, 8), item("A", 12, 2), item("B", 17, 3)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        # Line 1: A (y2), B (y3) -> x order A, B; line 2: C (y8).
        assert cells[1].text == "A B C"
        assert cells[1].source_ocr_indices == [1, 2, 0]


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


class TestTinyLeadingTokenTolerance:
    """D-34: the visual-line tolerance anchored on the FIRST token's
    height, so a tiny leading token (punctuation-height) shrank the
    tolerance and split otherwise aligned tokens into separate lines,
    reordering the reading sequence."""

    @staticmethod
    def tiny(text, cx, cy):
        return {"text": text, "box": [[cx - 2, cy - 1], [cx + 2, cy - 1],
                                      [cx + 2, cy + 1], [cx - 2, cy + 1]]}

    def test_tiny_leading_token_does_not_split_aligned_tokens(self):
        # A comma-height token (h=2, cy=4) leads the line; A and B
        # (h=6, cy=5/6) sit within one visual line of it. First-token
        # anchoring gave a 1 px tolerance and pushed B to a second line,
        # so B jumped behind the comma in reading order.
        items = [self.tiny(",", 18, 4), item("A", 11, 5), item("B", 14, 6)]
        cells, _ = assign_ocr_to_cells(make_grid(), items)
        assert cells[1].text == "A B ,"
        assert cells[1].source_ocr_indices == [1, 2, 0]


class TestTallTokenAdversarial:
    """Review pass on the D-34 fix: the tallest-token anchor must not
    merge genuinely separate neighboring rows when one region is
    unusually tall. Separation is only observable through reading order
    (cell text joins lines with spaces), so each test uses a cx ordering
    that reverses across the line boundary."""

    @staticmethod
    def grid():
        return GridGeometry(row_edges=[0, 30, 60], col_edges=[0, 30, 60])

    @staticmethod
    def item(text, cx, cy, h):
        return {"text": text, "box": [[cx - 5, cy - h // 2], [cx + 5, cy - h // 2],
                                      [cx + 5, cy + h // 2], [cx - 5, cy + h // 2]]}

    def _cell(self, items):
        cells, _ = assign_ocr_to_cells(self.grid(), items)
        return cells[1]

    def test_normal_rows_beyond_tolerance_stay_separate(self):
        # A(cy=4, cx=45) line 1; B(cy=9, cx=31), C(cy=10, cx=38) line 2.
        # Diff 5 > 0.5 * 6: separate -> "A B C". A false merge of all
        # three would order by x: "B C A".
        items = [self.item("A", 45, 4, 6), self.item("B", 31, 9, 6),
                 self.item("C", 38, 10, 6)]
        assert self._cell(items).text == "A B C"

    def test_tall_token_does_not_absorb_clearly_separate_row(self):
        # TALL(h=20, cy=10, cx=45) anchors tolerance at 10; the next row
        # sits at cy=24/25 (center diff 14/15 > 10, vertical ranges do
        # not overlap the tall region) -> separate lines -> "TALL B C".
        # A false merge would order by x: "B C TALL".
        items = [self.item("TALL", 45, 10, 20), self.item("B", 31, 24, 6),
                 self.item("C", 38, 25, 6)]
        assert self._cell(items).text == "TALL B C"

    def test_reading_order_with_tall_token_preserved(self):
        # One visual line mixing a tall region and normal tokens keeps
        # x order; a later row stays after it.
        items = [self.item("TALL", 31, 10, 20), self.item("A", 40, 12, 6),
                 self.item("B", 50, 13, 6), self.item("Z", 35, 24, 6)]
        assert self._cell(items).text == "TALL A B Z"

    def test_overlapping_neighbor_row_merges_by_design(self):
        # A neighbor whose vertical range overlaps the tall region's
        # range (here 4 px of the 6 px row) is the same visual line by
        # the project's 50%-overlap convention (mirrors extraction's
        # layout.group_lines rule) — merged is intentional, not a
        # false merge.
        items = [self.item("TALL", 31, 10, 20), self.item("B", 45, 19, 6)]
        assert self._cell(items).text == "TALL B"

    def test_tiny_leading_token_same_line_kept(self):
        # Keep the corrected D-34 behavior on the larger grid: a tiny
        # leading comma no longer splits the tokens that follow it.
        comma = {"text": ",", "box": [[31, 3], [33, 3], [33, 5], [31, 5]]}
        items = [comma, self.item("A", 40, 5, 6), self.item("B", 50, 6, 6)]
        assert self._cell(items).source_ocr_indices == [0, 1, 2]
