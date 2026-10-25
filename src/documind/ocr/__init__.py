"""OCR inference and result normalization for DocuMind."""

from .engine import OcrEngineError, PaddleOcrEngine
from .preprocessing import PreprocessingError, prepare_image
from .results import OcrResult, TextBox, normalize_result
from .validation import ValidationError, ValidatedInput, validate_image

__all__ = [
    "OcrEngineError",
    "PaddleOcrEngine",
    "PreprocessingError",
    "prepare_image",
    "OcrResult",
    "TextBox",
    "normalize_result",
    "ValidationError",
    "ValidatedInput",
    "validate_image",
]
