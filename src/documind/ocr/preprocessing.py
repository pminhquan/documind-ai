"""Minimal image preprocessing before OCR inference."""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image


class PreprocessingError(RuntimeError):
    """Raised when an image cannot be decoded or normalized."""


@contextmanager
def prepare_image(path: Path) -> Iterator[Path]:
    """Yield a path to an RGB-encoded image usable by the OCR engine.

    RGB files are passed through untouched. Other color modes (grayscale,
    palette, CMYK, alpha) are converted to RGB and written to a temporary
    PNG that is removed when the context exits.
    """
    try:
        with Image.open(path) as image:
            already_rgb = image.mode == "RGB"
    except OSError as exc:
        raise PreprocessingError(f"Cannot decode image '{path}': {exc}") from exc

    if already_rgb:
        yield path
        return

    fd, temp_name = tempfile.mkstemp(prefix="documind_", suffix=".png")
    os.close(fd)
    try:
        with Image.open(path) as image:
            image.convert("RGB").save(temp_name, format="PNG")
    except Exception as exc:
        # Broad cleanup (D-33): conversion failures are not limited to
        # OSError — e.g. PIL's DecompressionBombError — and the temp PNG
        # must never leak on any failure path.
        os.unlink(temp_name)
        raise PreprocessingError(
            f"Cannot convert image '{path}' to RGB: {exc}"
        ) from exc

    try:
        yield Path(temp_name)
    finally:
        Path(temp_name).unlink(missing_ok=True)
