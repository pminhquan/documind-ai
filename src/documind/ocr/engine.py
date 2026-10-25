"""Thin wrapper around PaddleOCR 3.x inference."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OcrEngineError(RuntimeError):
    """Raised when the OCR engine cannot be initialized or run."""


class PaddleOcrEngine:
    """CPU-first OCR engine based on pretrained PaddleOCR 3.x models.

    PP-OCRv5 text detection + recognition models are downloaded on first
    use into the user-level PaddleOCR cache (outside the repository).
    Document-classification stages are disabled to keep the baseline
    minimal and CPU-friendly.
    """

    def __init__(self, lang: str = "en", enable_mkldnn: bool = False) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrEngineError(
                "paddleocr is not installed. Run: pip install paddleocr"
            ) from exc

        try:
            self._ocr = PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                # oneDNN (MKLDNN) executor raises "ConvertPirAttribute2RuntimeAttribute
                # not support" with paddlepaddle 3.x CPU builds on Windows, so it is
                # disabled by default for compatibility.
                enable_mkldnn=enable_mkldnn,
            )
        except Exception as exc:  # paddle may raise its own error types
            raise OcrEngineError(f"Failed to initialize PaddleOCR: {exc}") from exc

    def predict(self, image_path: Path | str) -> list[dict]:
        """Run OCR on one image and return the raw PaddleOCR result list."""
        try:
            return self._ocr.predict(str(image_path))
        except Exception as exc:
            raise OcrEngineError(
                f"OCR inference failed for '{image_path}': {exc}"
            ) from exc
