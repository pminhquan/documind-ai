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

_engine_lock = threading.Lock()
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
    """Run OCR on an image path and return the structured result dict."""
    engine = _get_engine()
    try:
        raw_pages = engine.predict(str(source))
    except OcrEngineError as exc:
        raise DocumentProcessingError(str(exc)) from exc
    except Exception as exc:  # paddle runtime errors, defensive
        logger.exception("OCR inference failed")
        raise DocumentProcessingError(f"OCR inference failed: {exc}") from exc
    raw_page = raw_pages[0] if raw_pages else {}
    return normalize_result(raw_page, source=str(source)).to_dict()


def extract_invoice(ocr_document_data: dict) -> dict:
    """Extract an invoice from a saved OCR result dict (no inference)."""
    from ..extraction.extractor import extract

    result = extract(ocr_document_data, source=str(ocr_document_data.get("source", "")))
    return result.to_dict()


def tables_from_document(source: Path) -> dict:
    """Detect ruled tables in an image (runs OCR via the tables pipeline)."""
    try:
        return recognize_tables(source).to_dict()
    except TableRecognitionError as exc:
        raise DocumentProcessingError(str(exc)) from exc
    except OcrEngineError as exc:
        raise DocumentProcessingError(str(exc)) from exc


def process_unified(source: Path, workflows: list[str]) -> dict:
    """Run the requested workflows over one document."""
    result: dict = {"workflows": workflows, "source": str(source)}
    if "ocr" in workflows:
        result["ocr"] = ocr_document(source)
    if "invoice" in workflows:
        result["invoice"] = extract_invoice(result.get("ocr") or ocr_document(source))
    if "table" in workflows:
        result["tables"] = tables_from_document(source)
    return result
