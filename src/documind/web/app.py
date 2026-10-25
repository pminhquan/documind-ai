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
        Image.open(io.BytesIO(content)).verify()
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


def _table_result_from_payload(payload: dict) -> TableResult:
    """Accept a raw table result dict or one of the known export wrappers
    (``machine_output`` from the human-in-the-loop payload, or
    ``tables_result``)."""
    if "tables" not in payload:
        for wrapper in ("machine_output", "tables_result"):
            candidate = payload.get(wrapper)
            if isinstance(candidate, dict) and "tables" in candidate:
                payload = candidate
                break
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
            content = json.dumps(data, indent=2, ensure_ascii=False)
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
            )

        result = _table_result_from_payload(data)
        if kind in ("table-csv", "table-xlsx") and not result.tables:
            raise HTTPException(
                status_code=422,
                detail="No tables in the payload — nothing to export",
            )
        with tempfile.TemporaryDirectory(prefix="documind_export_") as tmp:
            target = Path(tmp) / safe_name
            from ..tables.exporters import export_csv, export_xlsx

            if kind == "table-csv":
                export_csv(result, target)
                media_type = "text/csv"
            else:
                export_xlsx(result, target)
                media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            # Exports are bounded by the upload size limit, so reading the
            # generated file into memory is safe; the temp dir is removed
            # on context exit, before Starlette would stat a FileResponse.
            return Response(
                content=target.read_bytes(),
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
