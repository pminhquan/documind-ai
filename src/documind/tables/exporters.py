"""Export table results to JSON, CSV, and editable XLSX."""

import csv
import json
from pathlib import Path

from .models import Table, TableResult


def table_matrix(table: Table) -> list[list[str]]:
    """Rebuild the rows x columns text grid from row-major cells."""
    matrix = [["" for _ in range(table.columns)] for _ in range(table.rows)]
    for cell in table.cells:
        matrix[cell.row_index][cell.column_index] = cell.text
    return matrix


def export_json(result: TableResult, path: str | Path, indent: int | None = 2) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.to_json(indent=indent), encoding="utf-8")
    return output


def _csv_paths(base: Path, table_count: int) -> list[Path]:
    if table_count <= 1:
        return [base]
    return [base.with_name(f"{base.stem}_t{index}{base.suffix}")
            for index in range(table_count)]


def export_csv(result: TableResult, path: str | Path) -> list[Path]:
    """Write one CSV per table; multiple tables get ``_t<i>`` suffixes."""
    base = Path(path)
    base.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table, target in zip(result.tables, _csv_paths(base, len(result.tables))):
        with target.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(table_matrix(table))
        written.append(target)
    return written


def export_xlsx(result: TableResult, path: str | Path) -> Path:
    """Write all tables into one workbook, one sheet per table."""
    from openpyxl import Workbook

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for table in result.tables:
        sheet = workbook.create_sheet(title=table.table_id)
        for row_index, row in enumerate(table_matrix(table), start=1):
            for col_index, value in enumerate(row, start=1):
                sheet.cell(row=row_index, column=col_index, value=value)
    workbook.save(output)
    return output
