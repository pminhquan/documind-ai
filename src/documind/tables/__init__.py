"""Ruled-table structure recognition baseline (M3A)."""

from .assign import assign_ocr_to_cells
from .exporters import export_csv, export_json, export_xlsx, table_matrix
from .geometry import GridGeometry, detect_table_grids
from .models import Rect, Table, TableCell, TableResult
from .pipeline import TableRecognitionError, recognize_tables

__all__ = [
    "assign_ocr_to_cells",
    "export_csv",
    "export_json",
    "export_xlsx",
    "table_matrix",
    "GridGeometry",
    "detect_table_grids",
    "Rect",
    "Table",
    "TableCell",
    "TableResult",
    "TableRecognitionError",
    "recognize_tables",
]
