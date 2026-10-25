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
        return recognize_tables(
            source,
            ocr_items=items if items is not None else None,
            ocr_runner=None if items is not None else _shared_ocr_runner,
        ).to_dict()
    except TableRecognitionError as exc:
        raise DocumentProcessingError(str(exc)) from exc
    except OcrEngineError as exc:
        raise DocumentProcessingError(str(exc)) from exc


def process_unified(source: Path, workflows: list[str]) -> dict:
    """Run the requested workflows over one document.

    OCR runs at most once: table assignment reuses the items produced for
    the OCR/invoice workflows.
    """
    result: dict = {"workflows": workflows, "source": str(source)}
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
