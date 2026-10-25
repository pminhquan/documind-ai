"""Ruled-table recognition pipeline: geometry + OCR assignment.

Geometry detection (OpenCV) is fully independent of OCR inference: pass
``ocr_items`` from a saved OCR JSON to test assignment without running
the model; omit it to run PaddleOCR on the image lazily.
"""

from pathlib import Path

from .assign import assign_ocr_to_cells
from .geometry import GridGeometry, detect_table_grids
from .models import Table, TableResult


class TableRecognitionError(RuntimeError):
    """Raised when the image cannot be decoded for table recognition."""


def _run_ocr(image_path: Path, lang: str) -> list[dict]:
    """Run the existing PaddleOCR pipeline and flatten to items."""
    from ..ocr.engine import PaddleOcrEngine
    from ..ocr.results import normalize_result

    engine = PaddleOcrEngine(lang=lang)
    raw_pages = engine.predict(image_path)
    raw_page = raw_pages[0] if raw_pages else {}
    ocr_result = normalize_result(raw_page, source=str(image_path))
    return [
        {"text": item.text, "confidence": item.confidence, "box": item.box}
        for item in ocr_result.items
    ]


def recognize_tables(
    image_path: str | Path,
    ocr_items: list[dict] | None = None,
    lang: str = "en",
) -> TableResult:
    """Detect ruled tables in ``image_path`` and fill cells with OCR text.

    ``ocr_items`` accepts items from a saved ``documind-ocr`` JSON
    ({"text", "confidence", "box"}); when omitted, PaddleOCR runs on the
    image. Warnings report unassigned regions and multi-table images;
    text is never invented for empty cells.
    """
    image_path = Path(image_path)
    image = _load_image(image_path)

    grids: list[GridGeometry] = detect_table_grids(image)
    warnings: list[str] = []
    if not grids:
        warnings.append("no ruled table detected in the image")
        return TableResult(source_image=str(image_path), tables=[], warnings=warnings)
    if len(grids) > 1:
        warnings.append(f"{len(grids)} table regions detected")

    if ocr_items is None:
        ocr_items = _run_ocr(image_path, lang)

    tables: list[Table] = []
    for index, grid in enumerate(grids):
        cells, assign_warnings = assign_ocr_to_cells(grid, ocr_items)
        tables.append(
            Table(
                table_id=f"table_{index}",
                source_image=str(image_path),
                rows=grid.rows,
                columns=grid.columns,
                cells=cells,
                warnings=assign_warnings,
            )
        )
    return TableResult(source_image=str(image_path), tables=tables, warnings=warnings)


def _load_image(image_path: Path) -> "cv2.typing.MatLike":  # noqa: F821
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        raise TableRecognitionError(f"Cannot decode image '{image_path}'")
    return image
