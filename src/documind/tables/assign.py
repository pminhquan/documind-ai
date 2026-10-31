"""Assignment of OCR regions to reconstructed table cells.

Matching is purely geometric: an OCR region joins the cell containing
its box center; when the center falls outside every cell (e.g. a box
slightly overshooting a rule), the cell with the largest box/cell
intersection area wins. Regions matching no cell at all are reported
as unassigned — never dropped silently, never forced into a cell.

Text is never invented: a cell without assigned regions stays "".
"""

from .geometry import GridGeometry
from .models import Rect, TableCell

UNASSIGNABLE = -1

# Two OCR regions share a visual line when their vertical centers differ
# by at most this fraction of the smaller box height (vertical jitter
# tolerance). Lines are ordered top-to-bottom; tokens within a line by
# horizontal center.
LINE_TOLERANCE = 0.5


def _region_center(item: dict) -> tuple[float, float] | None:
    box = item.get("box")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return None
    return sum(xs) / 4.0, sum(ys) / 4.0


def _region_rect(item: dict) -> Rect | None:
    box = item.get("box")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return None
    return Rect(
        x=int(min(xs)), y=int(min(ys)), w=int(max(xs) - min(xs)), h=int(max(ys) - min(ys))
    )


def _box_height(item: dict) -> float:
    box = item.get("box")
    try:
        ys = [float(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return 0.0
    return max(ys) - min(ys)


def _reading_order(members: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """Order ``(index, item)`` pairs top-to-bottom, left-to-right within
    each visual line.

    Regions whose vertical centers differ by more than
    ``LINE_TOLERANCE`` of the tallest box height seen in the current line
    or the incoming region start a new line; tokens within a line are
    ordered by horizontal center. Anchoring on the tallest height (not
    the first token's) keeps a tiny leading token (e.g. a comma) from
    shrinking the tolerance and splitting otherwise aligned tokens into
    separate lines (D-34). Regions without a usable box keep their
    original relative order at the end.
    """
    boxed: list[tuple[float, float, int, dict]] = []
    unboxed: list[tuple[int, dict]] = []
    for index, item in members:
        center = _region_center(item)
        if center is None:
            unboxed.append((index, item))
        else:
            boxed.append((center[1], center[0], index, item))  # (cy, cx)
    boxed.sort(key=lambda entry: (entry[0], entry[1]))

    ordered: list[tuple[int, dict]] = []
    line: list[tuple[float, int, dict]] = []  # (cx, index, item)
    line_cy = line_height = 0.0

    def flush() -> None:
        nonlocal line
        ordered.extend((index, item) for _, index, item in sorted(line))
        line = []

    for cy, cx, index, item in boxed:
        height = _box_height(item)
        if line and abs(cy - line_cy) > LINE_TOLERANCE * max(line_height, height):
            flush()
        if not line:
            line_cy = cy
        line_height = max(line_height, height)
        line.append((cx, index, item))
    flush()
    ordered.extend(unboxed)
    return ordered


def assign_ocr_to_cells(
    grid: GridGeometry, ocr_items: list[dict]
) -> tuple[list[TableCell], list[str]]:
    """Return ``(cells_in_row_major_order, warnings)`` for one grid."""
    cells: dict[tuple[int, int], list[tuple[int, dict]]] = {}
    unassigned: list[int] = []

    for index, item in enumerate(ocr_items):
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        center = _region_center(item)
        target: tuple[int, int] | None = None
        if center is not None:
            for row, col, rect in grid.cells():
                if rect.contains_point(*center):
                    target = (row, col)
                    break
        if target is None:
            # Fall back to the largest box/cell overlap.
            region = _region_rect(item)
            if region is not None:
                best_area, best_cell = 0, None
                for row, col, rect in grid.cells():
                    area = rect.intersection_area(region)
                    if area > best_area:
                        best_area, best_cell = area, (row, col)
                if best_area > 0:
                    target = best_cell
        if target is None:
            unassigned.append(index)
            continue
        cells.setdefault(target, []).append((index, item))

    warnings: list[str] = []
    if unassigned:
        warnings.append(
            f"{len(unassigned)} OCR region(s) outside the detected grid "
            f"(indices: {unassigned})"
        )

    table_cells: list[TableCell] = []
    for row, col, rect in grid.cells():
        ordered = _reading_order(cells.get((row, col), []))
        text = " ".join(str(pair[1].get("text")) for pair in ordered).strip()
        confidences = [
            float(pair[1]["confidence"])
            for pair in ordered
            if pair[1].get("confidence") is not None
        ]
        table_cells.append(
            TableCell(
                row_index=row,
                column_index=col,
                text=text,
                bounding_box=rect.to_polygon(),
                source_ocr_indices=[pair[0] for pair in ordered],
                confidence=(
                    sum(confidences) / len(confidences) if confidences else None
                ),
            )
        )
    return table_cells, warnings
