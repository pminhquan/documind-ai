"""JSON / CSV / XLSX export tests."""

import csv
import json

from documind.tables.exporters import (
    export_csv,
    export_json,
    export_xlsx,
    table_matrix,
)
from documind.tables.models import Table, TableCell, TableResult


def make_result(tables=1):
    def cell(r, c, text):
        return TableCell(
            row_index=r, column_index=c, text=text,
            bounding_box=[[c * 10, r * 10], [c * 10 + 10, r * 10],
                          [c * 10 + 10, r * 10 + 10], [c * 10, r * 10 + 10]],
            source_ocr_indices=[r * 2 + c] if text else [],
            confidence=0.9 if text else None,
        )

    def build(index):
        return Table(
            table_id=f"table_{index}",
            source_image="img.png",
            rows=2,
            columns=2,
            cells=[cell(0, 0, "Item"), cell(0, 1, "Qty"),
                   cell(1, 0, "Coffee"), cell(1, 1, "")],
            warnings=[],
        )

    return TableResult(
        source_image="img.png",
        tables=[build(i) for i in range(tables)],
        warnings=[],
    )


class TestTableMatrix:
    def test_matrix_preserves_empty_cells(self):
        assert table_matrix(make_result().tables[0]) == [
            ["Item", "Qty"],
            ["Coffee", ""],
        ]


class TestJsonExport:
    def test_round_trip(self, tmp_path):
        path = export_json(make_result(), tmp_path / "out.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["source_image"] == "img.png"
        assert data["tables"][0]["rows"] == 2
        cell = data["tables"][0]["cells"][0]
        assert cell["text"] == "Item"
        assert cell["row_index"] == 0 and cell["column_index"] == 0
        assert len(cell["bounding_box"]) == 4
        assert cell["confidence"] == 0.9
        empty = data["tables"][0]["cells"][3]
        assert empty["text"] == "" and empty["confidence"] is None


class TestCsvExport:
    def test_single_table_uses_exact_path(self, tmp_path):
        written = export_csv(make_result(), tmp_path / "out.csv")
        assert written == [tmp_path / "out.csv"]
        with written[0].open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        assert rows == [["Item", "Qty"], ["Coffee", ""]]

    def test_multiple_tables_get_suffixes(self, tmp_path):
        written = export_csv(make_result(tables=2), tmp_path / "out.csv")
        assert [p.name for p in written] == ["out_t0.csv", "out_t1.csv"]
        with written[0].open(encoding="utf-8", newline="") as handle:
            assert list(csv.reader(handle)) == [["Item", "Qty"], ["Coffee", ""]]


class TestXlsxExport:
    def test_workbook_is_readable_and_editable(self, tmp_path):
        from openpyxl import load_workbook

        path = export_xlsx(make_result(tables=2), tmp_path / "out.xlsx")
        workbook = load_workbook(path)
        assert workbook.sheetnames == ["table_0", "table_1"]
        sheet = workbook["table_0"]
        assert sheet.cell(row=1, column=1).value == "Item"
        assert sheet.cell(row=1, column=2).value == "Qty"
        assert sheet.cell(row=2, column=1).value == "Coffee"
        assert sheet.cell(row=2, column=2).value in ("", None)
