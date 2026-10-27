"""Local-first FastAPI application for DocuMind AI.

Security posture (local-first, default binding 127.0.0.1):
- Uploads are untrusted: strict size limit, extension allowlist, decoded
  content check via Pillow, safe temp storage with cleanup on every path.
- Inference is serialized on a single lazy engine (PaddleOCR is not
  thread-safe) — bounded concurrency by design.
- No CORS middleware is enabled by default; no public deployment.
- OCR text never enters routine logs.
"""

import csv
import io
import json
import logging
import re
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .. import __version__
from ..tables.models import Table, TableCell, TableResult
from . import service
from .schemas import (
    HealthResponse,
    InvoiceResponse,
    OcrResponse,
    TableResponse,
    UnifiedResponse,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
STATIC_DIR = Path(__file__).parent / "static"

# Resource limits: uploads are decoded-checked for pixel budget, exports
# are bounded so a hostile payload cannot force expensive allocation.
MAX_IMAGE_DIMENSION = 10_000
MAX_IMAGE_PIXELS = 30_000_000
MAX_EXPORT_TABLES = 50
MAX_TABLE_DIMENSION = 500
MAX_EXPORT_CELLS = 20_000
CORRECTION_PATH_RE = re.compile(r"^tables\[(\d+)\]\.cells\[(\d+)\]\[(\d+)\]$")
XML_ILLEGAL_CHARS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xslt_safe_text(value) -> str:
    return XML_ILLEGAL_CHARS_RE.sub("", "" if value is None else str(value))

DEFAULT_EXPORT_NAMES = {
    "ocr-json": "ocr-result.json",
    "ocr-txt": "ocr-result.txt",
    "invoice-json": "invoice-result.json",
    "invoice-csv": "invoice.csv",
    "invoice-xlsx": "invoice.xlsx",
    "table-json": "tables-result.json",
    "table-csv": "tables.csv",
    "table-xlsx": "tables.xlsx",
    "batch-zip": "batch-exports.zip",
}
EXPORT_KINDS = frozenset(DEFAULT_EXPORT_NAMES)
MAX_BATCH_EXPORTS = 10


class UploadValidationError(HTTPException):
    pass


def _read_and_validate_upload(upload: UploadFile,
                              content: bytes | None = None) -> Path:
    """Validate an upload and persist it to a temp file; caller must clean up.

    When ``content`` is pre-read (by endpoints that sniff PDFs first) it is
    used directly. Raises HTTPException(413/415/400) with friendly messages.
    """
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            status_code=415,
            detail=f"Unsupported file type '{extension or '(none)'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    if content is None:
        content = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError(
            status_code=413,
            detail=f"File too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    if not content:
        raise UploadValidationError(status_code=400, detail="Empty upload")

    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
        if max(width, height) > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
            raise UploadValidationError(
                status_code=413,
                detail=f"Image dimensions too large ({width}x{height}). Limit: "
                f"{MAX_IMAGE_DIMENSION}px per side / {MAX_IMAGE_PIXELS // 1_000_000} MP",
            )
    except UploadValidationError:
        raise
    except Exception as exc:
        raise UploadValidationError(
            status_code=400, detail="Upload is not a decodable image"
        ) from exc

    # delete=False: the file is handed to the processing pipeline and
    # unlinked in the endpoint's finally block.
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
        prefix="documind_upload_", suffix=extension, delete=False
    )
    handle.write(content)
    handle.close()
    return Path(handle.name)


def _apply_table_corrections(payload: dict) -> TableResult:
    """Build a corrected :class:`TableResult` from a HITL payload.

    ``user_corrections`` keys must be exactly ``tables[T].cells[R][C]``
    with T/R/C inside the machine output's bounds; the machine result is
    never mutated — corrected values are applied to a fresh copy. Invalid
    or out-of-bounds paths are rejected with 422 (no silent ignoring, no
    arbitrary object paths).
    """
    result = _table_result_from_payload(payload)
    corrections = payload.get("user_corrections")
    if corrections in (None, {}):
        return result

    if not isinstance(corrections, dict):
        raise HTTPException(status_code=422,
                            detail="'user_corrections' must be an object")

    cells_by_position: dict[tuple[int, int, int], TableCell] = {}
    for table_index, table in enumerate(result.tables):
        for cell in table.cells:
            cells_by_position[(table_index, cell.row_index, cell.column_index)] = cell

    for raw_path, value in corrections.items():
        match = CORRECTION_PATH_RE.match(str(raw_path))
        if not match:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid correction path {raw_path!r}: must look like "
                "'tables[0].cells[1][2]'",
            )
        table_index, row_index, column_index = map(int, match.groups())
        cell = cells_by_position.get((table_index, row_index, column_index))
        if cell is None:
            raise HTTPException(
                status_code=422,
                detail=f"Correction {raw_path!r}: cell coordinates out of bounds",
            )
        cell.text = "" if value is None else str(value)
    return result


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise HTTPException(status_code=422, detail=detail)


def _payload_int(value, context: str) -> int:
    """Strict integer extraction: bool is an int subclass but is never a
    valid dimension/coordinate in a client payload."""
    _require(isinstance(value, int) and not isinstance(value, bool),
             f"{context} must be an integer")
    return value


_TABLE_CELL_FIELDS = frozenset({
    "row_index", "column_index", "text", "bounding_box",
    "source_ocr_indices", "confidence",
})


def _table_from_payload(index: int, table) -> Table:
    """Validate one client table entry before any dataclass construction.

    Every field the exporters touch is checked here so malformed payloads
    fail with a stable 422 instead of an uncontrolled 500 from
    ``int()``, ``TableCell(**cell)`` or ``table_matrix`` indexing.
    Duplicate coordinates are tolerated (last write wins in the matrix);
    everything structurally invalid is rejected up front.
    """
    context = f"tables[{index}]"
    _require(isinstance(table, dict), f"{context} must be an object")
    rows = _payload_int(table.get("rows", 0), f"{context}.rows")
    columns = _payload_int(table.get("columns", 0), f"{context}.columns")
    _require(0 <= rows <= MAX_TABLE_DIMENSION
             and 0 <= columns <= MAX_TABLE_DIMENSION,
             f"{context} exceeds the {MAX_TABLE_DIMENSION}x"
             f"{MAX_TABLE_DIMENSION} dimension limit")
    table_id = table.get("table_id", f"table_{index}")
    _require(isinstance(table_id, str), f"{context}.table_id must be a string")
    warnings = table.get("warnings", [])
    _require(isinstance(warnings, list), f"{context}.warnings must be a list")
    cells_raw = table.get("cells", [])
    _require(isinstance(cells_raw, list), f"{context}.cells must be a list")

    cells: list[TableCell] = []
    for cell_index, cell in enumerate(cells_raw):
        cell_context = f"{context}.cells[{cell_index}]"
        _require(isinstance(cell, dict), f"{cell_context} must be an object")
        unknown = set(cell) - _TABLE_CELL_FIELDS
        _require(not unknown,
                 f"{cell_context} has unknown fields: {sorted(unknown)}")
        row_index = _payload_int(cell.get("row_index"),
                                 f"{cell_context}.row_index")
        column_index = _payload_int(cell.get("column_index"),
                                    f"{cell_context}.column_index")
        _require(0 <= row_index < rows and 0 <= column_index < columns,
                 f"{cell_context} coordinates outside the "
                 f"{rows}x{columns} table")
        text = cell.get("text", "")
        _require(isinstance(text, str), f"{cell_context}.text must be a string")
        bounding_box = cell.get("bounding_box")
        _require(isinstance(bounding_box, list),
                 f"{cell_context}.bounding_box must be a list")
        source_ocr_indices = cell.get("source_ocr_indices", [])
        _require(isinstance(source_ocr_indices, list),
                 f"{cell_context}.source_ocr_indices must be a list")
        cells.append(TableCell(
            row_index=row_index, column_index=column_index, text=text,
            bounding_box=bounding_box, source_ocr_indices=source_ocr_indices,
            confidence=cell.get("confidence"),
        ))
    return Table(
        table_id=table_id, source_image=str(table.get("source_image", "")),
        rows=rows, columns=columns, cells=cells, warnings=list(warnings),
    )


def _table_result_from_payload(payload: dict) -> TableResult:
    """Accept a raw table result dict or one of the known export wrappers
    (``machine_output`` from the human-in-the-loop payload, or
    ``tables_result``). Enforces bounded table/cell counts and validates
    every table entry before materialization."""
    if "tables" not in payload:
        for wrapper in ("machine_output", "tables_result"):
            candidate = payload.get(wrapper)
            if isinstance(candidate, dict) and "tables" in candidate:
                payload = candidate
                break
    tables = payload.get("tables", [])
    _require(isinstance(tables, list), "'tables' must be a list")
    _require(len(tables) <= MAX_EXPORT_TABLES,
             f"Too many tables ({len(tables)}; limit {MAX_EXPORT_TABLES})")
    payload_warnings = payload.get("warnings", [])
    _require(isinstance(payload_warnings, list), "'warnings' must be a list")
    validated = [_table_from_payload(index, table)
                 for index, table in enumerate(tables)]
    total_cells = sum(table.rows * table.columns for table in validated)
    _require(total_cells <= MAX_EXPORT_CELLS,
             f"Too many cells ({total_cells}; limit {MAX_EXPORT_CELLS})")
    return TableResult(
        source_image=str(payload.get("source_image", "")),
        tables=validated,
        warnings=list(payload_warnings),
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("DocuMind web app starting (local-first; binds 127.0.0.1 by default)")
    yield
    service.reset_engine()



INVOICE_SCALAR_KEYS = (
    "supplier", "invoice_number", "invoice_date", "currency", "subtotal",
    "tax", "discount", "total", "payment_amount", "change_amount",
)
INVOICE_ITEM_KEYS = ("description", "quantity", "unit_price", "line_total")
INVOICE_ITEM_PATH_RE = re.compile(r"^line_items\[(\d+)\]\.(\w+)$")


def _apply_invoice_corrections(invoice: dict, corrections: dict | None) -> dict:
    """Deep-copy an invoice dict with validated HITL corrections applied.

    Keys are client paths (invoice.total / invoice.line_items[0].qty);
    unknown paths or out-of-range item indices are rejected with 422.
    """
    corrected = json.loads(json.dumps(invoice or {}))
    for raw_path, value in (corrections or {}).items():
        path = str(raw_path)
        path = path.removeprefix("invoice.")
        if path in INVOICE_SCALAR_KEYS:
            corrected[path] = None if value in (None, "") else str(value)
            continue
        item_match = INVOICE_ITEM_PATH_RE.match(path)
        if not item_match:
            raise HTTPException(status_code=422,
                                detail=f"Invalid correction path {raw_path!r}")
        index, field = int(item_match.group(1)), item_match.group(2)
        items = corrected.get("line_items") or []
        if field not in INVOICE_ITEM_KEYS or index >= len(items):
            raise HTTPException(
                status_code=422,
                detail=f"Correction {raw_path!r}: line item out of bounds",
            )
        items[index][field] = None if value in (None, "") else str(value)
    return corrected


def _invoice_csv_content(invoice: dict) -> bytes:
    from ..tables.exporters import _csv_safe

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Field", "Value"])
    for key in INVOICE_SCALAR_KEYS:
        value = invoice.get(key)
        writer.writerow([key, _csv_safe("" if value is None else str(value))])
    writer.writerow([])
    writer.writerow(["Line items"])
    writer.writerow(list(INVOICE_ITEM_KEYS))
    for item in invoice.get("line_items") or []:
        writer.writerow([
            _csv_safe("" if item.get(key) is None else str(item.get(key)))
            for key in INVOICE_ITEM_KEYS
        ])
    return buffer.getvalue().encode("utf-8")


def _invoice_xlsx_content(invoice: dict) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Invoice"
    for row_index, key in enumerate(INVOICE_SCALAR_KEYS, start=1):
        value = invoice.get(key)
        sheet.cell(row=row_index, column=1, value=key).data_type = "s"
        safe_value = _xslt_safe_text(value)
        value_cell = sheet.cell(row=row_index, column=2, value=safe_value)
        value_cell.data_type = "s"
    item_start = len(INVOICE_SCALAR_KEYS) + 2
    sheet.cell(row=item_start, column=1, value="Line items").data_type = "s"
    for column, key in enumerate(INVOICE_ITEM_KEYS, start=1):
        sheet.cell(row=item_start + 1, column=column, value=key).data_type = "s"
    for offset, item in enumerate(invoice.get("line_items") or [], start=1):
        for column, key in enumerate(INVOICE_ITEM_KEYS, start=1):
            cell = sheet.cell(row=item_start + 1 + offset, column=column,
                              value=_xslt_safe_text(item.get(key)))
            cell.data_type = "s"
    target = io.BytesIO()
    workbook.save(target)
    return target.getvalue()


def _export_csv(result, path: Path) -> list[Path]:
    from ..tables.exporters import export_csv

    return export_csv(result, path)


def _export_xlsx(result, path: Path) -> Path:
    from ..tables.exporters import export_xlsx

    return export_xlsx(result, path)


def _build_export(kind: str, data: dict) -> tuple[bytes, str, str]:
    """Generate export bytes for one kind: (content, media_type, name).

    JSON kinds pass through untouched so human-in-the-loop payloads keep
    machine output and corrections separate. CSV/XLSX materialize
    corrections into a fresh copy; formula-injection policy re-applied.
    """
    if kind in ("ocr-json", "invoice-json", "table-json"):
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return (content.encode("utf-8"), "application/json",
                DEFAULT_EXPORT_NAMES[kind])

    if kind == "ocr-txt":
        text = data.get("full_text")
        if text is None:
            raise HTTPException(status_code=422,
                                detail="'data.full_text' is required for ocr-txt")
        return str(text).encode("utf-8"), "text/plain", "ocr-result.txt"

    if kind in ("invoice-csv", "invoice-xlsx"):
        machine = data.get("machine_output")
        invoice_raw = (machine or {}).get("invoice") or data.get("invoice") or {}
        invoice = _apply_invoice_corrections(invoice_raw, data.get("user_corrections"))
        content = (_invoice_csv_content(invoice) if kind == "invoice-csv"
                   else _invoice_xlsx_content(invoice))
        media_type = ("text/csv" if kind == "invoice-csv"
                      else "application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet")
        return content, media_type, DEFAULT_EXPORT_NAMES[kind]

    if kind in ("table-csv", "table-xlsx"):
        result = _apply_table_corrections(data)
        if not result.tables:
            raise HTTPException(status_code=422,
                                detail="No tables in the payload - nothing to export")
        media_type = ("text/csv" if kind == "table-csv"
                      else "application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet")
        if kind == "table-csv" and len(result.tables) > 1:
            with tempfile.TemporaryDirectory(prefix="documind_export_") as tmp:
                written = _export_csv(result, Path(tmp) / "tables.csv")
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in written:
                        archive.write(path, arcname=path.name)
                return buffer.getvalue(), "application/zip", "tables.zip"
        with tempfile.TemporaryDirectory(prefix="documind_export_") as tmp:
            target = Path(tmp) / DEFAULT_EXPORT_NAMES[kind]
            if kind == "table-csv":
                _export_csv(result, target)
            else:
                _export_xlsx(result, target)
            return target.read_bytes(), media_type, DEFAULT_EXPORT_NAMES[kind]

    if kind == "batch-zip":
        files = data.get("files")
        if not isinstance(files, list) or not files:
            raise HTTPException(status_code=422,
                                detail="'data.files' must be a non-empty list")
        if len(files) > MAX_BATCH_EXPORTS:
            raise HTTPException(
                status_code=422,
                detail=f"Too many batch files (limit {MAX_BATCH_EXPORTS})",
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            used_names: set[str] = set()
            for index, item in enumerate(files):
                if (not isinstance(item, dict)
                        or item.get("kind") not in EXPORT_KINDS - {"batch-zip"}
                        or not isinstance(item.get("data"), dict)):
                    raise HTTPException(
                        status_code=422,
                        detail=f"files[{index}] needs a valid 'kind' and 'data'",
                    )
                content, _, default_name = _build_export(item["kind"], item["data"])
                base_name = SAFE_FILENAME_RE.sub(
                    "_", str(item.get("filename") or default_name))
                # Budget the 80-char cap on the stem so truncation and
                # dedupe suffixes never eat the extension.
                stem, dot, extension = base_name.rpartition(".")
                if dot:
                    extension = extension[:16]
                    stem = stem[:max(1, 76 - len(extension))]
                    name = f"{stem}{dot}{extension}"
                else:
                    name = base_name[:80]
                name = name or f"file_{index}"
                unique, counter = name, 2
                while unique in used_names:
                    unique = (f"{stem}_{counter}{dot}{extension}"
                              if dot else f"{name}_{counter}")
                    counter += 1
                used_names.add(unique)
                archive.writestr(unique, content)
        return buffer.getvalue(), "application/zip", "batch-exports.zip"

    raise HTTPException(status_code=422, detail=f"Unknown export kind {kind!r}")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DocuMind AI",
        description="Local-first Document Intelligence API (OCR, invoice "
        "extraction, ruled-table recognition).",
        version=__version__,
        lifespan=_lifespan,
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            engine_loaded=service._engine is not None,
            version=__version__,
        )

    @app.post("/api/ocr", response_model=OcrResponse)
    def run_ocr(upload: Annotated[UploadFile, File(...)]) -> OcrResponse:
        temp_path = _read_and_validate_upload(upload)
        try:
            return OcrResponse.model_validate(service.ocr_document(temp_path))
        except service.DocumentProcessingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @app.post("/api/invoice", response_model=InvoiceResponse)
    def run_invoice(upload: Annotated[UploadFile, File(...)]) -> InvoiceResponse:
        temp_path = _read_and_validate_upload(upload)
        try:
            ocr_result = service.ocr_document(temp_path)
            return InvoiceResponse.model_validate(service.extract_invoice(ocr_result))
        except service.DocumentProcessingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @app.post("/api/table", response_model=TableResponse)
    def run_table(upload: Annotated[UploadFile, File(...)]) -> TableResponse:
        temp_path = _read_and_validate_upload(upload)
        try:
            return TableResponse.model_validate(service.tables_from_document(temp_path))
        except service.DocumentProcessingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @app.post("/api/process")
    def process_document(
        upload: Annotated[UploadFile, File(...)],
        workflow: str = Form("auto"),
    ):
        workflow_map = {
            "auto": ["ocr", "invoice", "table"],
            "ocr": ["ocr"],
            "invoice": ["ocr", "invoice"],
            "table": ["table"],
        }
        if workflow not in workflow_map:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown workflow {workflow!r}. Choose one of: {', '.join(workflow_map)}",
            )
        content = upload.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadValidationError(
                status_code=413,
                detail=f"File too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )
        if not content:
            raise UploadValidationError(status_code=400, detail="Empty upload")

        if content[:5] == b"%PDF-":
            # Multi-page PDF: per-page processing with partial success.
            with tempfile.TemporaryDirectory(prefix="documind_pdf_") as tmp:
                try:
                    return service.process_pdf(content, workflow_map[workflow],
                                               Path(tmp))
                except service.DocumentProcessingError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        temp_path = _read_and_validate_upload(upload, content)
        try:
            return UnifiedResponse.model_validate(
                service.process_unified(temp_path, workflow_map[workflow])
            )
        except service.DocumentProcessingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @app.post("/api/export")
    def export_results(payload: Annotated[dict, Body(...)]) -> Response:
        kind = payload.get("kind")
        if kind not in EXPORT_KINDS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown export kind {kind!r}. Choose one of: "
                f"{', '.join(sorted(EXPORT_KINDS))}",
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail="'data' must be an object")
        requested_name = str(payload.get("filename") or DEFAULT_EXPORT_NAMES[kind])
        safe_name = SAFE_FILENAME_RE.sub("_", requested_name)[:100] or "export.bin"
        content, media_type, default_name = _build_export(kind, data)
        if requested_name == DEFAULT_EXPORT_NAMES[kind]:
            safe_name = default_name
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
        )

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
