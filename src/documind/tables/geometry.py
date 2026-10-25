"""Ruled-table grid detection from images (OpenCV, no OCR).

Pipeline: grayscale -> inverted Otsu threshold -> morphological
extraction of long horizontal / vertical runs -> connected regions
(one per table) -> line positions via projection profiles -> cells as
intersections of consecutive row and column edges.

The module is independent of OCR inference so geometry can be unit
tested with synthetic images. It assumes complete, axis-aligned grid
lines (ruled tables); partial or borderless tables are out of scope
for this baseline.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from .models import Rect

MIN_KERNEL = 20          # shortest line run (px) that survives morphology
CLUSTER_GAP = 3          # max px gap between pixel rows of one line
LINE_COVERAGE = 0.6      # a grid line spans >= 60% of the region extent
MIN_REGION_SIZE = 40     # a table region is at least 40x40 px


@dataclass
class GridGeometry:
    """Reconstructed grid of one table region.

    ``row_edges`` / ``col_edges`` are sorted line positions (length
    rows+1 / cols+1); cells are the intersections of consecutive edges.
    """

    row_edges: list[int] = field(default_factory=list)
    col_edges: list[int] = field(default_factory=list)
    region: Rect = Rect(0, 0, 0, 0)

    @property
    def rows(self) -> int:
        return max(0, len(self.row_edges) - 1)

    @property
    def columns(self) -> int:
        return max(0, len(self.col_edges) - 1)

    def cell_rect(self, row_index: int, column_index: int) -> Rect:
        return Rect(
            x=self.col_edges[column_index],
            y=self.row_edges[row_index],
            w=self.col_edges[column_index + 1] - self.col_edges[column_index],
            h=self.row_edges[row_index + 1] - self.row_edges[row_index],
        )

    def cells(self) -> list[tuple[int, int, Rect]]:
        """All cells in row-major (reading) order."""
        return [
            (row, col, self.cell_rect(row, col))
            for row in range(self.rows)
            for col in range(self.columns)
        ]


def _binarize(image: np.ndarray) -> np.ndarray:
    """Inverted binary image: dark strokes become white (255)."""
    if image.ndim == 2:
        gray = image
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def _extract_lines(binary: np.ndarray, horizontal: bool) -> np.ndarray:
    """Keep only long line runs via erosion + dilation."""
    height, width = binary.shape[:2]
    kernel_len = max(MIN_KERNEL, (width if horizontal else height) // 15)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (kernel_len, 1) if horizontal else (1, kernel_len),
    )
    lines = cv2.erode(binary, kernel)
    return cv2.dilate(lines, kernel)


def _line_positions(mask: np.ndarray, axis: int, min_count: int) -> list[int]:
    """Cluster projection-profile peaks into line center positions."""
    projection = (mask > 0).sum(axis=axis)
    hits = np.where(projection >= min_count)[0]
    positions: list[list[int]] = []
    for value in hits:
        value = int(value)
        if positions and value - positions[-1][-1] <= CLUSTER_GAP:
            positions[-1].append(value)
        else:
            positions.append([value])
    return [int(round(sum(cluster) / len(cluster))) for cluster in positions]


def _dedupe_sorted(values: list[int], min_gap: int = 5) -> list[int]:
    """Drop line positions closer than ``min_gap`` px (degenerate slivers)."""
    result: list[int] = []
    for value in sorted(values):
        if not result or value - result[-1] >= min_gap:
            result.append(value)
    return result


def _table_regions(h_lines: np.ndarray, v_lines: np.ndarray) -> list[Rect]:
    """Bounding boxes of connected table regions, top-to-bottom."""
    combined = cv2.bitwise_or(h_lines, v_lines)
    combined = cv2.dilate(
        combined, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=2
    )
    contours, _ = cv2.findContours(
        combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= MIN_REGION_SIZE and h >= MIN_REGION_SIZE:
            regions.append(Rect(x=x, y=y, w=w, h=h))
    regions.sort(key=lambda rect: (rect.y, rect.x))
    return regions


def detect_table_grids(image: np.ndarray) -> list[GridGeometry]:
    """Detect ruled-table grids in a BGR (or grayscale) image.

    Returns one :class:`GridGeometry` per detected region in reading
    order; empty when the image contains no table.
    """
    binary = _binarize(image)
    h_lines = _extract_lines(binary, horizontal=True)
    v_lines = _extract_lines(binary, horizontal=False)

    grids: list[GridGeometry] = []
    for region in _table_regions(h_lines, v_lines):
        roi_h = h_lines[region.y : region.y2, region.x : region.x2]
        roi_v = v_lines[region.y : region.y2, region.x : region.x2]
        # Projection positions are ROI-relative; translate back to
        # absolute image coordinates with the region origin.
        row_edges = _line_positions(
            roi_h, axis=1, min_count=int(LINE_COVERAGE * region.w)
        )
        col_edges = _line_positions(
            roi_v, axis=0, min_count=int(LINE_COVERAGE * region.h)
        )
        row_edges = _dedupe_sorted(pos + region.y for pos in row_edges)
        col_edges = _dedupe_sorted(pos + region.x for pos in col_edges)
        if len(row_edges) < 2 or len(col_edges) < 2:
            continue  # not a usable grid
        grids.append(
            GridGeometry(row_edges=row_edges, col_edges=col_edges, region=region)
        )
    return grids
