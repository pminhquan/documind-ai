"""Assignment of OCR regions to reconstructed table cells.

Matching is purely geometric: an OCR region joins the cell containing
its box center; when the center falls outside every cell (e.g. a box
slightly overshooting a rule), the cell with the largest box/cell
intersection area wins. Regions matching no cell at all are reported
as unassigned — never dropped silently, never forced into a cell.

Text is never invented: a cell without assigned regions stays "".
"""

from .geometry import GridGeometry
from .models import TableCell, Rect

UNASSIGNABLE = -1


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
        members = cells.get((row, col), [])
        members.sort(
            key=lambda pair: (
                _region_center(pair[1]) or (float("inf"), float("inf"))
            )
        )
        text = " ".join(str(pair[1].get("text")) for pair in members).strip()
        confidences = [
            float(pair[1]["confidence"])
            for pair in members
            if pair[1].get("confidence") is not None
        ]
        table_cells.append(
            TableCell(
                row_index=row,
                column_index=col,
                text=text,
                bounding_box=rect.to_polygon(),
                source_ocr_indices=[pair[0] for pair in members],
                confidence=(
                    sum(confidences) / len(confidences) if confidences else None
                ),
            )
        )
    return table_cells, warnings
