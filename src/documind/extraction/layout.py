"""Reading-order reconstruction from OCR bounding boxes.

Groups flat OCR text regions into visual lines using vertical overlap,
then orders tokens inside a line by their x coordinate. Line order
follows the OCR engine's own reading order (top-to-bottom for our
detector); only within-line order is re-derived geometrically.
"""

from dataclasses import dataclass, field

from .parsing import normalize_text


@dataclass(frozen=True)
class OcrToken:
    """One OCR text region positioned in the page."""

    index: int  # position in the original OCR items list (for provenance)
    text: str
    box: tuple[tuple[float, float], ...] = ()

    @property
    def has_box(self) -> bool:
        return len(self.box) == 4

    @property
    def x0(self) -> float:
        return min(point[0] for point in self.box)

    @property
    def x1(self) -> float:
        return max(point[0] for point in self.box)

    @property
    def y0(self) -> float:
        return min(point[1] for point in self.box)

    @property
    def y1(self) -> float:
        return max(point[1] for point in self.box)

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


@dataclass
class VisualLine:
    """Tokens sharing one visual row, ordered left to right."""

    tokens: list[OcrToken] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(token.text for token in self.tokens)

    @property
    def has_box(self) -> bool:
        return any(token.has_box for token in self.tokens)

    @property
    def y0(self) -> float:
        return min(token.y0 for token in self.tokens if token.has_box)

    @property
    def y1(self) -> float:
        return max(token.y1 for token in self.tokens if token.has_box)

    @property
    def x1(self) -> float:
        return max(token.x1 for token in self.tokens if token.has_box)


def _normalize_box(box) -> tuple[tuple[float, float], ...]:
    """Coerce an OCR box (list of [x, y] pairs) to a tuple of tuples."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return ()
    try:
        return tuple((float(point[0]), float(point[1])) for point in box)
    except (TypeError, ValueError, IndexError):
        return ()


def _same_row(line: VisualLine, token: OcrToken) -> bool:
    """True when the token's vertical range overlaps the line by >= 50%."""
    overlap = min(line.y1, token.y1) - max(line.y0, token.y0)
    min_height = min(line.y1 - line.y0, token.height)
    return min_height > 0 and overlap / min_height >= 0.5


def group_lines(ocr_items: list) -> list[VisualLine]:
    """Group raw OCR ``items`` (dicts with text/box) into visual lines.

    Tokens without a usable box become single-token lines in their
    original order. A boxed token joins the most recent line it is fully
    to the right of when their rows overlap (reading-order merge).
    """
    tokens = []
    for index, item in enumerate(ocr_items):
        if not isinstance(item, dict):
            continue
        text = normalize_text(str(item.get("text") or ""))
        if not text:
            continue
        tokens.append(
            OcrToken(index=index, text=text, box=_normalize_box(item.get("box")))
        )

    lines: list[VisualLine] = []
    for token in tokens:
        if not token.has_box:
            lines.append(VisualLine(tokens=[token]))
            continue
        target = None
        for line in reversed(lines):
            if not line.tokens[0].has_box:
                continue
            if _same_row(line, token) and token.x0 >= line.x1 - 1.0:
                target = line
                break
        if target is not None:
            target.tokens.append(token)
        else:
            lines.append(VisualLine(tokens=[token]))

    for line in lines:
        line.tokens.sort(key=lambda t: (t.x0 if t.has_box else float(t.index), t.index))
    return lines
