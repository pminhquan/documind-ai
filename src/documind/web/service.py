"""Application service layer for the local web app.

Thin orchestration over the existing pipelines: OCR -> extraction ->
tables. No FastAPI imports here, so the service is reusable and testable
without the web stack. Heavy model initialization is lazy and guarded by
a lock — PaddleOCR inference is not thread-safe, so requests serialize
on the engine (bounded concurrency by design).
"""

import logging
import threading
from pathlib import Path

from ..ocr.engine import OcrEngineError, PaddleOcrEngine
from ..ocr.results import normalize_result
from ..tables.pipeline import TableRecognitionError, recognize_tables

logger = logging.getLogger(__name__)

# Web responses never carry server-local filesystem paths: uploads and
# PDF page renders live in temporary files that are deleted after the
# request, so their paths are both sensitive and meaningless to clients.
# Stable labels keep per-page identity without leaking locations.
WEB_SOURCE_LABEL = "upload"


def _safe_error(exc: Exception, source: Path) -> str:
    """Client-safe error text: the local source path never leaves the
    process. Underlying engine/pipeline errors embed the path they were
    handed; the exact string is replaced (targeted, not a global rewrite
    of message content)."""
    return str(exc).replace(str(source), WEB_SOURCE_LABEL)


_engine_lock = threading.Lock()
_inference_lock = threading.Lock()
_engine: PaddleOcrEngine | None = None


class DocumentProcessingError(RuntimeError):
    """Raised when a service operation fails; safe to show to the user."""


def _get_engine() -> PaddleOcrEngine:
    """Lazy, thread-safe singleton OCR engine."""
    global _engine
    with _engine_lock:
        if _engine is None:
            logger.info("initializing OCR engine (one-time)")
            _engine = PaddleOcrEngine()
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests)."""
    global _engine
    with _engine_lock:
        _engine = None


def ocr_document(source: Path) -> dict:
    """Run OCR on an image path and return the structured result dict.

    predict() is serialized on ``_inference_lock``: PaddleOCR is not
    thread-safe, so concurrent requests wait instead of entering the
    model simultaneously (bounded by one inference at a time).
    """
    engine = _get_engine()
    try:
        with _inference_lock:
            raw_pages = engine.predict(str(source))
    except OcrEngineError as exc:
        raise DocumentProcessingError(_safe_error(exc, source)) from exc
    except Exception as exc:  # paddle runtime errors, defensive
        logger.exception("OCR inference failed")
        raise DocumentProcessingError(
            _safe_error(Exception(f"OCR inference failed: {exc}"), source)
        ) from exc
    raw_page = raw_pages[0] if raw_pages else {}
    return normalize_result(raw_page, source=WEB_SOURCE_LABEL).to_dict()


def extract_invoice(ocr_document_data: dict) -> dict:
    """Extract an invoice from a saved OCR result dict (no inference)."""
    from ..extraction.extractor import extract

    result = extract(ocr_document_data, source=str(ocr_document_data.get("source", "")))
    return result.to_dict()


def _shared_ocr_runner(source: Path) -> list[dict]:
    """Runner contract matching the tables pipeline: items list only."""
    return ocr_document(source).get("items", [])


def tables_from_document(source: Path, ocr_items: dict | list | None = None) -> dict:
    """Detect ruled tables in an image.

    ``ocr_items`` (an ``{"items": [...]}`` OCR result) reuses OCR already
    produced for the same document instead of running inference again;
    otherwise OCR runs through the shared engine.
    """
    items = ocr_items.get("items") if isinstance(ocr_items, dict) else ocr_items
    try:
        result = recognize_tables(
            source,
            ocr_items=items if items is not None else None,
            ocr_runner=None if items is not None else _shared_ocr_runner,
        ).to_dict()
    except TableRecognitionError as exc:
        raise DocumentProcessingError(_safe_error(exc, source)) from exc
    except OcrEngineError as exc:
        raise DocumentProcessingError(_safe_error(exc, source)) from exc
    result["source_image"] = WEB_SOURCE_LABEL
    for table in result.get("tables", []):
        table["source_image"] = WEB_SOURCE_LABEL
    return result


def process_unified(source: Path, workflows: list[str]) -> dict:
    """Run the requested workflows over one document.

    OCR runs at most once: table assignment reuses the items produced for
    the OCR/invoice workflows.
    """
    result: dict = {"workflows": workflows, "source": WEB_SOURCE_LABEL}
    ocr_result = None
    if "ocr" in workflows or "invoice" in workflows or "table" in workflows:
        if "ocr" in workflows:
            ocr_result = ocr_document(source)
            result["ocr"] = ocr_result
    if "invoice" in workflows:
        result["invoice"] = extract_invoice(ocr_result or ocr_document(source))
    if "table" in workflows:
        result["tables"] = tables_from_document(source, ocr_items=ocr_result)
    return result


def process_pdf(content: bytes, workflows: list[str], output_dir: Path,
                max_pages: int = 10) -> dict:
    """Process a multi-page PDF page by page.

    The single-page invoice extractor does not understand cross-page
    relationships, so every workflow runs per page and results stay
    page-indexed. A page that fails is recorded in ``errors`` while other
    pages still produce results (partial success).
    """
    from .pdf import PdfError, render_pdf_pages

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        page_images = render_pdf_pages(content, output_dir, max_pages=max_pages)
    except PdfError as exc:
        raise DocumentProcessingError(str(exc)) from exc

    pages: list[dict] = []
    errors: list[str] = []
    for page_index, page_path in enumerate(page_images):
        try:
            pages.append({
                "page_index": page_index,
                **process_unified(page_path, workflows),
                "source": f"{WEB_SOURCE_LABEL}#page{page_index}",
            })
        except DocumentProcessingError as exc:
            errors.append(f"page {page_index}: {exc}")
            pages.append({"page_index": page_index, "error": str(exc)})
        finally:
            page_path.unlink(missing_ok=True)
    return {"kind": "pdf", "page_count": len(page_images),
            "workflows": workflows, "pages": pages, "errors": errors}
