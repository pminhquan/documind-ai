"""Vietnamese invoice extraction tests (M5C).

Extraction-level fixtures built as OCR-item dicts (no image rendering):
these validate label/monetary/date RULES, not Vietnamese OCR recognition
(see the reality check in docs/extraction-spec.md).
"""

from decimal import Decimal

import pytest

from documind.extraction import extract
from documind.extraction.parsing import parse_amount


def vi_doc(rows):
    """rows: list of lines; each line is a list of (text, x, y) cells."""
    items = []
    for row in rows:
        for text, x, y in row:
            items.append({"text": text, "box": [
                [x, y], [x + 8 * len(text), y],
                [x + 8 * len(text), y + 20], [x, y + 20]]})
    return {"engine": "fixture", "items": items}


FULL_VI_ROWS = [
    [("SIÊU THỊ MINIMART", 10, 10)],
    [("Địa chỉ: 01 Nguyễn Trãi, TP.HCM", 10, 40)],
    [("Số hóa đơn: 00001234", 10, 70)],
    [("Ngày lập: 25/10/2026", 10, 100)],
    [("SẢN PHẨM", 10, 130), ("SỐ LƯỢNG x ĐƠN GIÁ", 150, 130), ("THÀNH TIỀN", 330, 130)],
    [("NƯỚC SUỐI", 10, 160), ("2 x 5.000", 150, 160), ("10.000", 330, 160)],
    [("BÁNH MÌ", 10, 190), ("1 x 12.500", 150, 190), ("12.500", 330, 190)],
    [("TẠM TÍNH", 10, 240), ("22.500", 330, 240)],
    [("THUẾ GTGT 8%", 10, 270), ("1.800", 330, 270)],
    [("TỔNG CỘNG", 10, 300), ("24.300 đ", 330, 300)],
    [("TIỀN KHÁCH ĐƯA", 10, 330), ("50.000", 330, 330)],
    [("TIỀN THỪA", 10, 360), ("25.700", 330, 360)],
]


class TestVietnameseLabels:
    def test_full_diacritic_receipt(self):
        invoice = extract(vi_doc(FULL_VI_ROWS)).invoice
        assert invoice.supplier == "SIÊU THỊ MINIMART"
        assert invoice.invoice_number == "00001234"
        assert invoice.invoice_date.isoformat() == "2026-10-25"
        assert invoice.currency == "VND"  # from the standalone "đ" marker
        assert [i.description for i in invoice.line_items] == ["NƯỚC SUỐI", "BÁNH MÌ"]
        assert invoice.line_items[0].line_total == Decimal(10000)
        assert invoice.subtotal == Decimal(22500)
        assert invoice.tax == Decimal(1800)
        assert invoice.total == Decimal(24300)
        assert invoice.payment_amount == Decimal(50000)
        assert invoice.change_amount == Decimal(25700)
        assert invoice.validation_status == "ok"

    def test_no_diacritic_labels(self):
        rows = [r[:] for r in FULL_VI_ROWS]
        rows[3] = [("Ngay lap: 25-10-2026", 10, 100)]
        rows[7] = [("TAM TINH", 10, 240), ("22.500", 330, 240)]
        rows[9] = [("TONG CONG", 10, 300), ("24.300", 330, 300)]
        invoice = extract(vi_doc(rows)).invoice
        assert invoice.subtotal == Decimal(22500)
        assert invoice.total == Decimal(24300)
        assert invoice.invoice_date.isoformat() == "2026-10-25"

    def test_thanh_tien_maps_to_total(self):
        rows = [
            [("CỬA HÀNG AN NHƠN", 10, 10)],
            [("THÀNH TIỀN", 10, 100), ("15.000 đ", 330, 100)],
        ]
        invoice = extract(vi_doc(rows)).invoice
        assert invoice.total == Decimal(15000)

    def test_labelled_supplier(self):
        rows = [[("TÊN CỬA HÀNG: MINIMART", 10, 10)],
                [("TỔNG CỘNG", 10, 100), ("9.000", 330, 100)]]
        invoice = extract(vi_doc(rows)).invoice
        assert invoice.supplier == "MINIMART"

    def test_bare_label_line_is_not_supplier(self):
        rows = [[("ĐƠN VỊ BÁN HÀNG", 10, 10)],
                [("TỔNG TIỀN", 10, 100), ("9.000", 330, 100)]]
        invoice = extract(vi_doc(rows)).invoice
        assert invoice.supplier is None  # label line skipped, nothing fabricated


class TestVietnameseMoney:
    @pytest.mark.parametrize("text, expected", [
        ("1.234.567", "1234567"),
        ("1.234.567,89", "1234567.89"),
        ("1,234,567.89", "1234567.89"),
        ("125.000 đ", "125000"),
        ("125.000 VNĐ", "125000"),
        ("125000 VND", "125000"),
        ("₫125.000", "125000"),
    ])
    def test_formats(self, text, expected):
        assert parse_amount(text) == Decimal(expected)

    def test_dong_inside_word_is_not_currency_noise(self):
        # "đơn giá" must survive amount stripping untouched
        assert parse_amount("đơn giá") is None
        from documind.extraction.parsing import normalize_text
        assert normalize_text("đơn giá 5.000") == "đơn giá 5.000"

    def test_vnd_from_word_marker(self):
        rows = [[("MINIMART", 10, 10)],
                [("TỔNG CỘNG", 10, 100), ("125.000 VNĐ", 330, 100)]]
        assert extract(vi_doc(rows)).invoice.currency == "VND"


class TestVietnameseDates:
    @pytest.mark.parametrize("text, iso", [
        ("Ngày lập: 25/10/2026", "2026-10-25"),
        ("Ngày bán 05-01-2026", "2026-01-05"),
    ])
    def test_labelled_dates(self, text, iso):
        rows = [[("MINIMART", 10, 10)], [(text, 10, 100)]]
        assert extract(vi_doc(rows)).invoice.invoice_date.isoformat() == iso

    def test_invalid_date_is_not_fabricated(self):
        rows = [[("MINIMART", 10, 10)],
                [("Ngày lập: 32/13/2026", 10, 100)]]
        assert extract(vi_doc(rows)).invoice.invoice_date is None


class TestEnglishRegression:
    def test_english_receipt_unchanged(self):
        rows = [
            [("MINI MART EXPRESS", 10, 10)],
            [("TOTAL", 10, 100), ("9.57", 330, 100)],
        ]
        invoice = extract(vi_doc(rows)).invoice
        assert invoice.total == Decimal("9.57")
        assert invoice.supplier == "MINI MART EXPRESS"


class TestSummaryZoneOpeners:
    """Regression: SUMMARY_START_RE lacked thue/khach dua/tien mat, so a
    cash/tax row printed before the subtotal stayed inside the ITEM
    region: it became a bogus line item and tripped a false 'invalid'."""

    def test_cash_row_before_subtotal_is_not_a_line_item(self):
        rows = [
            [("CỬA HÀNG MINIMART", 10, 10)],
            [("Số hóa đơn: 00001234", 10, 40)],
            [("Ngày lập: 25/10/2026", 10, 70)],
            [("SOAP", 10, 100), ("2 x 2.50", 150, 100), ("5.00", 330, 100)],
            [("TIỀN MẶT:", 10, 130), ("5.00", 330, 130)],
            [("TẠM TÍNH", 10, 160), ("5.00", 330, 160)],
            [("TỔNG CỘNG", 10, 190), ("5.00", 330, 190)],
        ]
        invoice = extract(vi_doc(rows)).invoice
        assert [i.description for i in invoice.line_items] == ["SOAP"]
        assert invoice.payment_amount == Decimal("5.00")
        assert invoice.subtotal == Decimal("5.00")
        assert invoice.total == Decimal("5.00")
        assert invoice.validation_status == "ok"

    def test_bare_tax_row_opens_summary_zone(self):
        rows = [
            [("CỬA HÀNG MINIMART", 10, 10)],
            [("Số hóa đơn: 00001234", 10, 40)],
            [("Ngày lập: 25/10/2026", 10, 70)],
            [("SOAP", 10, 100), ("2 x 2.50", 150, 100), ("5.00", 330, 100)],
            [("THUẾ", 10, 130), ("1.800", 330, 130)],
            [("TỔNG CỘNG", 10, 160), ("6.800", 330, 160)],
        ]
        invoice = extract(vi_doc(rows)).invoice
        assert [i.description for i in invoice.line_items] == ["SOAP"]
        assert invoice.tax == Decimal(1800)
        assert invoice.total == Decimal(6800)
        assert invoice.validation_status == "ok"

    def test_merged_integer_total_vnd(self):
        rows = [
            [("CỬA HÀNG MINIMART", 10, 10)],
            [("Số hóa đơn: 00001234", 10, 40)],
            [("Ngày lập: 25/10/2026", 10, 70)],
            [("CA PHE", 10, 100), ("2 x 10.000", 150, 100), ("20.000", 330, 100)],
            [("TỔNG CỘNG: 97.200", 10, 130)],
        ]
        invoice = extract(vi_doc(rows)).invoice
        assert [i.line_total for i in invoice.line_items] == [Decimal(20000)]
        assert invoice.total == Decimal(97200)

    def test_label_only_supplier_line_falls_through(self):
        rows = [
            [("TÊN CỬA HÀNG:", 10, 10)],
            [("MINIMART", 10, 40)],
            [("TỔNG CỘNG", 10, 70), ("9.000", 330, 70)],
        ]
        invoice = extract(vi_doc(rows)).invoice
        assert invoice.supplier == "MINIMART"
