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


def validate_file(
    path: str | Path,
    *,
    extensions: frozenset[str],
    max_size_bytes: int,
) -> ValidatedInput:
    """Check that ``path`` is a readable file with an allowed extension and size.

    Raises:
        ValidationError: if the file is missing, unsupported, empty, or too large.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise ValidationError(f"Input file not found: {file_path}")
    if not file_path.is_file():
        raise ValidationError(f"Input path is not a file: {file_path}")

    extension = file_path.suffix.lower()
    if extension not in extensions:
        supported = ", ".join(sorted(extensions))
        raise ValidationError(
            f"Unsupported file format '{extension}'. Supported: {supported}"
        )

    size_bytes = file_path.stat().st_size
    if size_bytes == 0:
        raise ValidationError(f"Input file is empty: {file_path}")
    if size_bytes > max_size_bytes:
        raise ValidationError(
            f"Input file is too large ({size_bytes} bytes > {max_size_bytes} bytes): "
            f"{file_path}"
        )

    return ValidatedInput(path=file_path, size_bytes=size_bytes)


def validate_image(
    path: str | Path, max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES
) -> ValidatedInput:
    """Check that ``path`` is a readable image file within size limits."""
    return validate_file(
        path, extensions=SUPPORTED_EXTENSIONS, max_size_bytes=max_size_bytes
    )
