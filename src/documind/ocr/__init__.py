"""OCR inference and result normalization for DocuMind."""

from .engine import OcrEngineError, PaddleOcrEngine
from .preprocessing import PreprocessingError, prepare_image
from .results import OcrResult, TextBox, normalize_result
from .validation import ValidatedInput, ValidationError, validate_image

__all__ = [
    "OcrEngineError",
    "OcrResult",
    "PaddleOcrEngine",
    "PreprocessingError",
    "TextBox",
    "ValidatedInput",
    "ValidationError",
    "normalize_result",
    "prepare_image",
    "validate_image",
]
