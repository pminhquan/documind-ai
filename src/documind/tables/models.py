"""Typed models for ruled-table recognition results (M3A).

Geometry is expressed in integer pixel coordinates; text is never
invented for empty or unrecognized cells (``text`` stays ``""``).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    """Axis-aligned pixel rectangle."""

    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px < self.x2 and self.y <= py < self.y2

    def intersection_area(self, other: "Rect") -> int:
        overlap_w = min(self.x2, other.x2) - max(self.x, other.x)
        overlap_h = min(self.y2, other.y2) - max(self.y, other.y)
        return max(0, overlap_w) * max(0, overlap_h)

    def to_polygon(self) -> list[list[int]]:
        """Four corner points, matching the OCR result box convention."""
        return [
            [self.x, self.y],
            [self.x2, self.y],
            [self.x2, self.y2],
            [self.x, self.y2],
        ]


@dataclass
class TableCell:
    """One reconstructed table cell.

    ``source_ocr_indices`` lists positions in the OCR items array whose
    regions were assigned to this cell; ``text`` is their joined content
    (empty string for an empty cell). ``confidence`` is the mean of the
    assigned regions' confidences, or None when unavailable.
    """

    row_index: int
    column_index: int
    text: str
    bounding_box: list[list[int]]
    source_ocr_indices: list[int] = field(default_factory=list)
    confidence: float | None = None


@dataclass
class Table:
    table_id: str
    source_image: str
    rows: int
    columns: int
    cells: list[TableCell] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TableResult:
    source_image: str
    tables: list[Table] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_image": self.source_image,
            "tables": [
                {
                    "table_id": table.table_id,
                    "source_image": table.source_image,
                    "rows": table.rows,
                    "columns": table.columns,
                    "cells": [
                        {
                            "row_index": cell.row_index,
                            "column_index": cell.column_index,
                            "text": cell.text,
                            "bounding_box": cell.bounding_box,
                            "source_ocr_indices": list(cell.source_ocr_indices),
                            "confidence": cell.confidence,
                        }
                        for cell in table.cells
                    ],
                    "warnings": list(table.warnings),
                }
                for table in self.tables
            ],
            "warnings": list(self.warnings),
        }

    def to_json(self, indent: int | None = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
