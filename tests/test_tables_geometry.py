"""Geometry tests for ruled-table grid detection (no OCR involved)."""

import cv2
import numpy as np
import pytest

from documind.tables.geometry import detect_table_grids


def draw_grid(
    shape=(200, 260, 3),
    row_edges=(10, 60, 110, 160),
    col_edges=(10, 110, 210),
    offset=(0, 0),
):
    """White image with black ruled lines at the given edges."""
    image = np.full(shape, 255, dtype=np.uint8)
    dy, dx = offset
    for y in row_edges:
        cv2.line(image, (col_edges[0] + dx, y + dy), (col_edges[-1] + dx, y + dy),
                 (0, 0, 0), 2)
    for x in col_edges:
        cv2.line(image, (x + dx, row_edges[0] + dy), (x + dx, row_edges[-1] + dy),
                 (0, 0, 0), 2)
    return image


def close_to(values, expected, tolerance=3):
    assert len(values) == len(expected)
    for got, want in zip(values, expected):
        assert abs(got - want) <= tolerance, f"{values} vs {expected}"


class TestLineDetection:
    def test_detects_full_grid(self):
        grids = detect_table_grids(draw_grid())
        assert len(grids) == 1
        grid = grids[0]
        close_to(grid.row_edges, [10, 60, 110, 160])
        close_to(grid.col_edges, [10, 110, 210])
        assert grid.rows == 3
        assert grid.columns == 2

    def test_text_strokes_do_not_create_lines(self):
        image = draw_grid()
        # Simulate dense text strokes between the ruled lines.
        cv2.putText(image, "Hello World", (20, 45), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 1)
        cv2.putText(image, "Second Row", (20, 95), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 1)
        grids = detect_table_grids(image)
        assert len(grids) == 1
        assert grids[0].rows == 3 and grids[0].columns == 2

    def test_blank_image_has_no_tables(self):
        image = np.full((200, 200, 3), 255, dtype=np.uint8)
        assert detect_table_grids(image) == []

    def test_horizontal_lines_only_have_no_table(self):
        image = np.full((200, 260, 3), 255, dtype=np.uint8)
        for y in (10, 60, 110):
            cv2.line(image, (10, y), (250, y), (0, 0, 0), 2)
        assert detect_table_grids(image) == []

    def test_two_tables_detected_in_reading_order(self):
        image = draw_grid(shape=(420, 520, 3))
        image = draw_grid(
            shape=image.shape, row_edges=(10, 60, 110), col_edges=(10, 110, 210)
        )
        second = draw_grid(
            shape=image.shape,
            row_edges=(240, 300, 360),
            col_edges=(250, 360, 470),
        )
        combined = np.minimum(image, second)
        grids = detect_table_grids(combined)
        assert len(grids) == 2
        assert grids[0].region.y < grids[1].region.y
        assert (grids[0].rows, grids[0].columns) == (2, 2)
        assert (grids[1].rows, grids[1].columns) == (2, 2)


class TestCellReconstruction:
    def test_cells_row_major_order_and_coordinates(self):
        grids = detect_table_grids(draw_grid())
        cells = grids[0].cells()
        assert [cell[:2] for cell in cells] == [
            (0, 0), (0, 1),
            (1, 0), (1, 1),
            (2, 0), (2, 1),
        ]
        first = cells[0][2]
        assert first.x == pytest.approx(10, abs=3)
        assert first.y == pytest.approx(10, abs=3)
        assert first.w == pytest.approx(100, abs=5)
        assert first.h == pytest.approx(50, abs=5)

    def test_cell_rects_are_disjoint_and_cover_grid(self):
        grid = detect_table_grids(draw_grid())[0]
        cells = [rect for _, _, rect in grid.cells()]
        for i, a in enumerate(cells):
            for b in cells[i + 1:]:
                assert a.intersection_area(b) == 0
        total = sum(rect.w * rect.h for rect in cells)
        outer = grid.cells()[0][2]
        last = cells[-1]
        span_x = last.x2 - outer.x
        span_y = last.y2 - outer.y
        assert total == pytest.approx(span_x * span_y, rel=0.02)
