"""Normalization of PaddleOCR 3.x raw output into structured results."""

import json
from dataclasses import asdict, dataclass, field

DEFAULT_ENGINE_NAME = "paddleocr"


@dataclass(frozen=True)
class TextBox:
    """One recognized text region.

    ``box`` holds the four corner points of the detected region as
    ``[[x1, y1], [x2, y2], [x3, y3], [x4, y4]]`` in pixel coordinates.
    """

    text: str
    confidence: float
    box: list[list[float]] = field(default_factory=list)


@dataclass
class OcrResult:
    """Structured OCR output for a single image."""

    source: str
    engine: str = DEFAULT_ENGINE_NAME
    items: list[TextBox] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """All recognized lines joined by newlines, in reading order."""
        return "\n".join(item.text for item in self.items)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "engine": self.engine,
            "items": [asdict(item) for item in self.items],
            "full_text": self.full_text,
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def normalize_result(
    raw: dict | None, source: str = "", engine: str = DEFAULT_ENGINE_NAME
) -> OcrResult:
    """Convert one raw PaddleOCR 3.x result mapping into an :class:`OcrResult`.

    ``raw`` is a single element of the list returned by
    ``PaddleOCR.predict()``. PaddleOCR 3.x exposes recognized texts,
    per-text confidence scores, and text-line polygons under the
    ``rec_texts`` / ``rec_scores`` / ``rec_polys`` keys.
    """
    raw = raw or {}
    texts = list(raw.get("rec_texts") or [])
    scores = list(raw.get("rec_scores") or [])
    polygons = raw.get("rec_polys")
    if polygons is None:
        polygons = raw.get("dt_polys") or []

    items: list[TextBox] = []
    for index, text in enumerate(texts):
        confidence = float(scores[index]) if index < len(scores) else 0.0
        box: list[list[float]] = []
        if index < len(polygons):
            box = [[float(point[0]), float(point[1])] for point in polygons[index]]
        items.append(TextBox(text=str(text), confidence=confidence, box=box))

    return OcrResult(source=str(source), engine=engine, items=items)
