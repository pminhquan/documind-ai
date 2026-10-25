"""Ruled-table structure recognition baseline (M3A)."""

from .assign import assign_ocr_to_cells
from .exporters import export_csv, export_json, export_xlsx, table_matrix
from .geometry import GridGeometry, detect_table_grids
from .models import Rect, Table, TableCell, TableResult
from .pipeline import TableRecognitionError, recognize_tables

__all__ = [
    "GridGeometry",
    "Rect",
    "Table",
    "TableCell",
    "TableRecognitionError",
    "TableResult",
    "assign_ocr_to_cells",
    "detect_table_grids",
    "export_csv",
    "export_json",
    "export_xlsx",
    "recognize_tables",
    "table_matrix",
]
