"""Validation of OCR input images."""

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
)
DEFAULT_MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


class ValidationError(ValueError):
    """Raised when an input image does not satisfy OCR input requirements."""


@dataclass(frozen=True)
class ValidatedInput:
    """A validated OCR input image."""

    path: Path
    size_bytes: int


def validate_image(
    path: str | Path, max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES
) -> ValidatedInput:
    """Check that ``path`` is a readable image file within size limits.

    Raises:
        ValidationError: if the file is missing, unsupported, empty, or too large.
    """
    image_path = Path(path)

    if not image_path.exists():
        raise ValidationError(f"Input file not found: {image_path}")
    if not image_path.is_file():
        raise ValidationError(f"Input path is not a file: {image_path}")

    extension = image_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValidationError(
            f"Unsupported image format '{extension}'. Supported: {supported}"
        )

    size_bytes = image_path.stat().st_size
    if size_bytes == 0:
        raise ValidationError(f"Input file is empty: {image_path}")
    if size_bytes > max_size_bytes:
        raise ValidationError(
            f"Input file is too large ({size_bytes} bytes > {max_size_bytes} bytes): "
            f"{image_path}"
        )

    return ValidatedInput(path=image_path, size_bytes=size_bytes)
