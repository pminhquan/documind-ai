"""PDF rendering for multi-page processing (M5B).

pypdfium2 renders page images from untrusted PDF bytes with hard bounds:
a page-count limit, a per-page pixel budget, and friendly errors for
encrypted or malformed files. Page images are written to a caller-owned
temporary directory (cleanup is the caller's responsibility).
"""

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
MAX_PAGES = 10
RENDER_SCALE = 2.0  # ~144 DPI from a 72 DPI page
MAX_PAGE_PIXELS = 30_000_000


class PdfError(ValueError):
    """Raised for encrypted, malformed, or oversized PDFs (safe message)."""


def is_pdf(content: bytes) -> bool:
    return content[:5] == PDF_MAGIC


def render_pdf_pages(content: bytes, output_dir: Path, max_pages: int = MAX_PAGES,
                     scale: float = RENDER_SCALE) -> list[Path]:
    """Render every page to a PNG inside ``output_dir`` (must exist).

    Returns page image paths in deterministic page order (0-based index
    encoded in the filename). Raises :class:`PdfError` for malformed,
    encrypted, or over-limit documents.
    """
    if not is_pdf(content):
        raise PdfError("Not a PDF document")
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise PdfError("PDF support is not installed (pip install pypdfium2)") from exc

    try:
        document = pdfium.PdfDocument(io.BytesIO(content))
    except Exception as exc:
        message = str(exc)
        if "password" in message.lower() or "encrypt" in message.lower():
            raise PdfError("PDF is encrypted — provide a decrypted copy") from exc
        raise PdfError(f"Malformed PDF: {message}") from exc

    try:
        page_count = len(document)
        if page_count == 0:
            raise PdfError("PDF contains no pages")
        if page_count > max_pages:
            raise PdfError(
                f"PDF has {page_count} pages (limit {max_pages}) — split the "
                "document and process the parts separately"
            )
        paths: list[Path] = []
        for index in range(page_count):
            try:
                page = document[index]
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
            except Exception as exc:
                raise PdfError(f"Failed to render page {index}: {exc}") from exc
            if pil_image.width * pil_image.height > MAX_PAGE_PIXELS:
                raise PdfError(
                    f"Page {index} is too large to process "
                    f"({pil_image.width}x{pil_image.height}; limit "
                    f"{MAX_PAGE_PIXELS // 1_000_000} MP) — lower the scan DPI"
                )
            target = output_dir / f"page_{index:03d}.png"
            pil_image.save(target, format="PNG")
            paths.append(target)
            logger.info("rendered PDF page %s (%dx%d)", index,
                        pil_image.width, pil_image.height)
        return paths
    finally:
        document.close()
