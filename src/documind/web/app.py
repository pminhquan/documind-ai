"""Local-first FastAPI application for DocuMind AI.

Security posture (local-first, default binding 127.0.0.1):
- Uploads are untrusted: strict size limit, extension allowlist, decoded
  content check via Pillow, safe temp storage with cleanup on every path.
- Inference is serialized on a single lazy engine (PaddleOCR is not
  thread-safe) — bounded concurrency by design.
- No CORS middleware is enabled by default; no public deployment.
- OCR text never enters routine logs.
"""

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
EXPORT_KINDS = frozenset({"ocr-json", "invoice-json", "table-json", "table-csv", "table-xlsx"})
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

DEFAULT_EXPORT_NAMES = {
    "ocr-json": "ocr-result.json",
    "invoice-json": "invoice-result.json",
    "table-json": "tables-result.json",
    "table-csv": "tables.csv",
    "table-xlsx": "tables.xlsx",
}


class UploadValidationError(HTTPException):
    pass


def _read_and_validate_upload(upload: UploadFile) -> Path:
    """Persist a validated upload to a temp file; caller must clean up.

    Raises HTTPException(413/415/400) with friendly messages on any
    violation. Returns the temp file path.
    """
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            status_code=415,
            detail=f"Unsupported file type '{extension or '(none)'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

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


def _table_result_from_payload(payload: dict) -> TableResult:
    """Accept a raw table result dict or one of the known export wrappers
    (``machine_output`` from the human-in-the-loop payload, or
    ``tables_result``). Enforces bounded table/cell counts."""
    if "tables" not in payload:
        for wrapper in ("machine_output", "tables_result"):
            candidate = payload.get(wrapper)
            if isinstance(candidate, dict) and "tables" in candidate:
                payload = candidate
                break
    tables = payload.get("tables", [])
    if not isinstance(tables, list):
        raise HTTPException(status_code=422, detail="'tables' must be a list")
    if len(tables) > MAX_EXPORT_TABLES:
        raise HTTPException(
            status_code=422,
            detail=f"Too many tables ({len(tables)}; limit {MAX_EXPORT_TABLES})",
        )
    total_cells = 0
    for index, table in enumerate(tables):
        rows, columns = int(table.get("rows", 0)), int(table.get("columns", 0))
        if rows > MAX_TABLE_DIMENSION or columns > MAX_TABLE_DIMENSION:
            raise HTTPException(
                status_code=422,
                detail=f"tables[{index}] exceeds the {MAX_TABLE_DIMENSION}x"
                f"{MAX_TABLE_DIMENSION} dimension limit",
            )
        total_cells += rows * columns
    if total_cells > MAX_EXPORT_CELLS:
        raise HTTPException(
            status_code=422,
            detail=f"Too many cells ({total_cells}; limit {MAX_EXPORT_CELLS})",
        )
    return TableResult(
        source_image=str(payload.get("source_image", "")),
        tables=[
            Table(
                table_id=table.get("table_id", f"table_{index}"),
                source_image=str(table.get("source_image", "")),
                rows=int(table.get("rows", 0)),
                columns=int(table.get("columns", 0)),
                cells=[TableCell(**cell) for cell in table.get("cells", [])],
                warnings=list(table.get("warnings", [])),
            )
            for index, table in enumerate(payload.get("tables", []))
        ],
        warnings=list(payload.get("warnings", [])),
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("DocuMind web app starting (local-first; binds 127.0.0.1 by default)")
    yield
    service.reset_engine()


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

    @app.post("/api/process", response_model=UnifiedResponse)
    def process_document(
        upload: Annotated[UploadFile, File(...)],
        workflow: str = Form("auto"),
    ) -> UnifiedResponse:
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
        temp_path = _read_and_validate_upload(upload)
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

        if kind.endswith("-json"):
            # JSON exports pass through as-is: for HITL payloads this
            # preserves BOTH machine output and user corrections.
            content = json.dumps(data, indent=2, ensure_ascii=False)
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
            )

        from ..tables.exporters import export_csv, export_xlsx

        # CSV/XLSX materialize user corrections into a fresh copy of the
        # machine result; the original machine output is not mutated.
        result = _apply_table_corrections(data)
        if not result.tables:
            raise HTTPException(
                status_code=422,
                detail="No tables in the payload — nothing to export",
            )

        media_type = ("text/csv" if kind == "table-csv"
                      else "application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet")
        if kind == "table-csv" and len(result.tables) > 1:
            # The CSV exporter writes one file per table (_t0, _t1, ...);
            # package them into an in-memory ZIP with sanitized entries.
            with tempfile.TemporaryDirectory(prefix="documind_export_") as tmp:
                written = export_csv(result, Path(tmp) / "tables.csv")
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in written:
                        archive.write(path, arcname=path.name)
                content = buffer.getvalue()
            safe_name = "tables.zip"
            media_type = "application/zip"
        else:
            with tempfile.TemporaryDirectory(prefix="documind_export_") as tmp:
                target = Path(tmp) / safe_name
                if kind == "table-csv":
                    export_csv(result, target)
                else:
                    export_xlsx(result, target)
                # Exports are bounded by the payload limits, so reading the
                # generated file into memory is safe; the temp dir is removed
                # on context exit, before Starlette would stat a FileResponse.
                content = target.read_bytes()
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
