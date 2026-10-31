"""Extraction pipeline tests using synthetic OCR JSON fixtures.

Every fixture has known expected outputs; nothing here runs an OCR model
or claims model accuracy — these tests validate the deterministic rules.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from documind.extraction import (
    STATUS_INVALID,
    STATUS_OK,
    STATUS_REVIEW,
    OcrInputError,
    extract,
    load_ocr_document,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ocr"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def money(value: str) -> Decimal:
    return Decimal(value)


class TestNormalReceipt:
    @pytest.fixture
    def result(self):
        return extract(load_fixture("normal_receipt.json"), source="fixture")

    def test_header_fields(self, result):
        invoice = result.invoice
        assert invoice.supplier == "MINI MART EXPRESS"
        assert invoice.invoice_number == "00001234"
        assert invoice.invoice_date.isoformat() == "2026-10-25"
        assert invoice.currency == "USD"

    def test_line_items_with_layout(self, result):
        items = result.invoice.line_items
        assert [(i.description, i.quantity, i.unit_price, i.line_total) for i in items] == [
            ("SOAP", money("2"), money("2.50"), money("5.00")),
            ("MILK 1L", money("1"), money("2.50"), money("2.50")),
            ("BREAD", money("1"), money("1.20"), money("1.20")),
        ]

    def test_summary_amounts_and_status(self, result):
        invoice = result.invoice
        assert invoice.subtotal == money("8.70")
        assert invoice.tax == money("0.87")
        assert invoice.total == money("9.57")
        assert invoice.payment_amount == money("10.00")
        assert invoice.change_amount == money("0.43")
        assert invoice.validation_status == STATUS_OK
        assert invoice.validation_errors == []

    def test_provenance_links_to_ocr_regions(self, result):
        prov = result.provenance
        assert prov["total"].text == "9.57"
        assert prov["total"].box[0] == [327.0, 494.0]
        assert prov["supplier"].ocr_index == 0
        assert prov["line_items[0].line_total"].text == "5.00"

    def test_json_serialization_keeps_decimal_scale(self, result):
        data = json.loads(result.to_json())
        assert data["invoice"]["total"] == "9.57"
        assert data["invoice"]["line_items"][0]["unit_price"] == "2.50"
        assert data["provenance"]["total"]["ocr_index"] >= 0


class TestMissingFields:
    def test_absent_fields_stay_null(self):
        result = extract(load_fixture("missing_fields.json"))
        invoice = result.invoice
        assert invoice.supplier == "MINI MART EXPRESS"
        assert invoice.total == money("9.57")
        assert invoice.invoice_number is None
        assert invoice.invoice_date is None
        assert invoice.currency is None
        assert invoice.line_items == []
        assert invoice.subtotal is None
        assert invoice.tax is None
        assert invoice.discount is None
        assert invoice.payment_amount is None
        assert invoice.change_amount is None
        assert invoice.validation_status == STATUS_OK


class TestDateFormats:
    @pytest.mark.parametrize(
        "date_text, expected",
        [
            ("Date: 2026-10-25", "2026-10-25"),
            ("Date: 25/10/2026", "2026-10-25"),
            ("Date: 25.10.2026", "2026-10-25"),
            ("Date: 05 Apr 2026", "2026-04-05"),
            ("Date: 10/25/2026", "2026-10-25"),  # month-first fallback
        ],
    )
    def test_date_normalization(self, date_text, expected):
        document = {"items": [{"text": "MINI MART", "box": []},
                              {"text": date_text, "box": []}]}
        result = extract(document)
        assert result.invoice.invoice_date.isoformat() == expected

    def test_unparseable_date_stays_none(self):
        document = {"items": [{"text": "Date: sometime soon", "box": []}]}
        assert extract(document).invoice.invoice_date is None


class TestValidationSemantics:
    """Regression: completeness and arithmetic consistency are judged
    separately. An empty or identification-less document must never be
    reported as plain 'ok'.

    Sufficiently complete (M2 baseline) = at least one monetary anchor
    (grand total, subtotal, or a line item with a line_total) AND at
    least one identification field (supplier, invoice number, or date).
    Optional fields (tax, discount, payment, change) never affect this.
    """

    def test_empty_ocr_is_review_required(self):
        result = extract({"items": []})
        invoice = result.invoice
        assert invoice.validation_status == STATUS_REVIEW
        assert any("incomplete" in e for e in invoice.validation_errors)

    def test_total_only_is_review_required(self):
        document = {"items": [{"text": "TOTAL 9.57", "box": []}]}
        result = extract(document)
        assert result.invoice.total == Decimal("9.57")
        assert result.invoice.validation_status == STATUS_REVIEW
        assert any("incomplete" in e for e in result.invoice.validation_errors)

    def test_supplier_plus_total_is_ok(self):
        result = extract(load_fixture("missing_fields.json"))
        assert result.invoice.validation_status == STATUS_OK

    def test_fully_valid_invoice_is_ok(self):
        result = extract(load_fixture("normal_receipt.json"))
        assert result.invoice.validation_status == STATUS_OK

    def test_missing_optional_fields_do_not_affect_status(self):
        # discounts fixture has no payment/change/line items at all
        result = extract(load_fixture("discounts.json"))
        assert result.invoice.payment_amount is None
        assert result.invoice.change_amount is None
        assert result.invoice.validation_status == STATUS_OK

    def test_partial_line_totals_do_not_report_subtotal_error(self):
        # SOAP has no printed line total; the old subtotal check summed
        # only the present totals and falsely flagged a mismatch.
        document = {"items": [
            {"text": "MINI MART", "box": [[0, 0], [60, 0], [60, 20], [0, 20]]},
            {"text": "ITEM QTY x PRICE",
             "box": [[0, 30], [110, 30], [110, 50], [0, 50]]},
            {"text": "SOAP", "box": [[0, 60], [40, 60], [40, 80], [0, 80]]},
            {"text": "2 x 2.50", "box": [[50, 60], [110, 60], [110, 80], [50, 80]]},
            {"text": "MILK", "box": [[0, 90], [40, 90], [40, 110], [0, 110]]},
            {"text": "1 x 2.50", "box": [[50, 90], [110, 90], [110, 110], [50, 110]]},
            {"text": "2.50", "box": [[120, 90], [160, 90], [160, 110], [120, 110]]},
            {"text": "SUBTOTAL", "box": [[0, 130], [60, 130], [60, 150], [0, 150]]},
            {"text": "5.00", "box": [[120, 130], [160, 130], [160, 150], [120, 150]]},
            {"text": "TOTAL", "box": [[0, 160], [50, 160], [50, 180], [0, 180]]},
            {"text": "5.00", "box": [[120, 160], [160, 160], [160, 180], [120, 180]]},
        ]}
        result = extract(document)
        invoice = result.invoice
        assert len(invoice.line_items) == 2
        assert invoice.line_items[0].line_total is None
        assert not any("subtotal" in e for e in invoice.validation_errors)
        assert invoice.validation_status == STATUS_OK


class TestProvenanceCompleteness:
    """Regression: line items lacked quantity/unit_price provenance, and
    multi-line description provenance pointed at the wrong region."""

    def test_quantity_and_unit_price_provenance_exist(self):
        result = extract(load_fixture("normal_receipt.json"))
        prov = result.provenance
        # Both values live in the same OCR region ("2 x 2.50").
        assert prov["line_items[0].quantity"].text == "2 x 2.50"
        assert prov["line_items[0].unit_price"].text == "2 x 2.50"
        assert prov["line_items[0].quantity"].ocr_index == \
            prov["line_items[0].unit_price"].ocr_index

    def test_multiline_description_provenance_points_to_description_region(self):
        result = extract(load_fixture("multiline_description.json"))
        prov = result.provenance["line_items[0].description"]
        # The description text came from the earlier "SOAP LAVENDER" row,
        # not from the merged qty/price row.
        assert prov.text == "SOAP LAVENDER"

    def test_total_provenance_comes_from_same_document(self):
        document = load_fixture("normal_receipt.json")
        result = extract(document)
        prov = result.provenance["total"]
        assert Decimal(prov.text) == result.invoice.total
        assert prov.text == document["items"][prov.ocr_index]["text"]
        assert prov.box == [
            [float(x), float(y)]
            for x, y in document["items"][prov.ocr_index]["box"]
        ]


class TestMonetaryRegression:
    """Regression: MONEY_TOKEN_RE capped ungrouped integers at 1-3 digits,
    so the re.search fallback extracted only a substring of larger amounts
    (1234.56 -> 234.56). Amounts must be captured completely or not at all."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("1234.56", "1234.56"),
            ("12345.67", "12345.67"),
            ("1234567,89", "1234567.89"),
            ("1,234.56", "1234.56"),
            ("1.234,56", "1234.56"),
            ("TOTAL 1234.56", "1234.56"),
            ("TOTAL 12345.67", "12345.67"),
        ],
    )
    def test_rightmost_amount_finds_complete_value(self, text, expected):
        from documind.extraction.extractor import _rightmost_amount
        from documind.extraction.layout import OcrToken, VisualLine

        line = VisualLine(tokens=[OcrToken(index=0, text=text, box=())])
        assert _rightmost_amount(line) == Decimal(expected)

    def test_rightmost_complete_value_wins_over_earlier_candidate(self):
        from documind.extraction.extractor import _rightmost_amount
        from documind.extraction.layout import OcrToken, VisualLine

        line = VisualLine(tokens=[OcrToken(index=0, text="TOTAL 1.50 12345.67", box=())])
        assert _rightmost_amount(line) == Decimal("12345.67")

    def test_malformed_amount_is_not_silently_reinterpreted(self):
        from documind.extraction.extractor import _rightmost_amount
        from documind.extraction.layout import OcrToken, VisualLine

        line = VisualLine(tokens=[OcrToken(index=0, text="TOTAL 12.34.56.78", box=())])
        assert _rightmost_amount(line) is None

    def test_extracted_total_is_complete_value(self):
        # Same-row boxes make the OCR regions group into one visual line,
        # mirroring the real OCR output for a total row.
        document = {"items": [
            {"text": "MINI MART", "box": []},
            {"text": "TOTAL", "box": [[0, 0], [50, 0], [50, 20], [0, 20]]},
            {"text": "1234.56", "box": [[60, 0], [120, 0], [120, 20], [60, 20]]},
        ]}
        assert extract(document).invoice.total == Decimal("1234.56")

    def test_merged_total_cell_is_complete_value(self):
        document = {"items": [
            {"text": "MINI MART", "box": []},
            {"text": "TOTAL 12345.67", "box": []},
        ]}
        assert extract(document).invoice.total == Decimal("12345.67")


class TestMonetarySeparators:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("1,234.56", "1234.56"),  # US thousands
            ("1.234,56", "1234.56"),  # EU thousands
            ("12,30", "12.30"),  # EU decimal comma
            ("1,234", "1234"),  # thousands group
            ("1.234", "1234"),  # thousands group (3 decimals)
            ("12.30", "12.30"),
            ("$13.53", "13.53"),
        ],
    )
    def test_amount_parsing(self, text, expected):
        from documind.extraction.parsing import parse_amount

        assert parse_amount(text) == money(expected)

    def test_eu_separator_fixture(self):
        result = extract(load_fixture("eu_separators.json"))
        invoice = result.invoice
        assert invoice.invoice_date.isoformat() == "2026-10-25"
        assert invoice.line_items[0].quantity == money("2")
        assert invoice.line_items[0].unit_price == money("500.00")
        assert invoice.line_items[0].line_total == money("1000.00")
        assert invoice.subtotal == money("1000.00")
        assert invoice.tax == money("234.56")
        assert invoice.total == money("1234.56")
        assert invoice.validation_status == STATUS_OK


class TestMissingBoxes:
    def test_extraction_without_boxes(self):
        result = extract(load_fixture("no_boxes.json"))
        invoice = result.invoice
        assert invoice.supplier == "MINI MART EXPRESS"
        assert invoice.total == money("9.57")
        # provenance entries exist but carry empty boxes
        assert result.provenance["total"].box == []


class TestValidation:
    def test_incorrect_grand_total_is_invalid(self):
        result = extract(load_fixture("bad_total.json"))
        invoice = result.invoice
        assert invoice.total == money("99.99")
        assert invoice.validation_status == STATUS_INVALID
        assert any("total != subtotal + tax" in e for e in invoice.validation_errors)

    def test_duplicate_total_labels_same_value(self):
        result = extract(load_fixture("duplicate_totals.json"))
        invoice = result.invoice
        assert invoice.total == money("5.00")
        assert invoice.validation_status == STATUS_REVIEW
        assert any("TOTAL" in e for e in invoice.validation_errors)

    def test_duplicate_totals_with_different_values_keep_bottom_most(self):
        document = {"items": [
            {"text": "TOTAL 9.57", "box": []},
            {"text": "TOTAL 12.00", "box": []},
        ]}
        result = extract(document)
        assert result.invoice.total == money("12.00")
        assert result.invoice.validation_status == STATUS_REVIEW

    def test_discount_and_tax_arithmetic(self):
        result = extract(load_fixture("discounts.json"))
        invoice = result.invoice
        assert invoice.subtotal == money("10.00")
        assert invoice.discount == money("1.00")
        assert invoice.tax == money("0.90")
        assert invoice.total == money("9.90")  # 10.00 - 1.00 + 0.90
        assert invoice.validation_status == STATUS_OK


class TestAmbiguity:
    def test_ambiguous_quantity_not_fabricated(self):
        result = extract(load_fixture("ambiguous_line.json"))
        item = result.invoice.line_items[0]
        assert item.description == "SOAP X2"
        assert item.quantity is None  # "X2" is not an explicit qty x price row
        assert item.unit_price is None
        assert item.line_total == money("5.00")
        assert result.invoice.validation_status == STATUS_OK


class TestEdgeCases:
    def test_empty_ocr_output(self):
        result = extract(load_fixture("empty_items.json"))
        invoice = result.invoice
        assert invoice.supplier is None
        assert invoice.line_items == []
        assert invoice.total is None
        # Completeness and arithmetic are judged separately: an empty
        # document has no inconsistency but is not "ok" either.
        assert invoice.validation_status == STATUS_REVIEW
        assert any("incomplete" in e for e in invoice.validation_errors)

    def test_malformed_json_rejected(self):
        with pytest.raises(OcrInputError, match="Malformed JSON"):
            load_ocr_document(FIXTURES / "malformed.json")

    def test_non_object_json_rejected(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(OcrInputError, match="must be an object"):
            load_ocr_document(path)

    def test_oversized_ocr_json_rejected_at_load(self, tmp_path, monkeypatch):
        """D-28: MAX_OCR_JSON_BYTES is enforced at the load boundary."""
        import documind.extraction.extractor as extractor_module

        monkeypatch.setattr(extractor_module, "MAX_OCR_JSON_BYTES", 16)
        path = tmp_path / "big.json"
        path.write_text(json.dumps({"items": [{"text": "x" * 64}]}),
                        encoding="utf-8")
        with pytest.raises(OcrInputError, match="input limit"):
            load_ocr_document(path)

    def test_ocr_json_at_exact_limit_is_accepted(self, tmp_path, monkeypatch):
        import documind.extraction.extractor as extractor_module

        monkeypatch.setattr(extractor_module, "MAX_OCR_JSON_BYTES", 16)
        path = tmp_path / "exact.json"
        content = '{"items": []}   '  # exactly 16 bytes
        assert len(content.encode("utf-8")) == 16
        path.write_text(content, encoding="utf-8")
        assert load_ocr_document(path) == {"items": []}

    def test_multi_line_product_description(self):
        result = extract(load_fixture("multiline_description.json"))
        item = result.invoice.line_items[0]
        assert item.description == "SOAP LAVENDER 90G"
        assert item.quantity == money("2")
        assert item.unit_price == money("2.50")
        assert item.line_total == money("5.00")
        assert result.invoice.validation_status == STATUS_OK

    def test_merges_split_header_cells(self):
        # The real OCR splits the header row into two regions.
        result = extract(load_fixture("normal_receipt.json"))
        assert len(result.invoice.line_items) == 3


def ocr_doc(lines):
    """lines: list of rows, each a list of (text, x) cells; y auto-steps."""
    items = []
    y = 10
    for cells in lines:
        for text, x in cells:
            items.append({"text": text, "box": [
                [x, y], [x + 8 * len(text), y],
                [x + 8 * len(text), y + 20], [x, y + 20]]})
        y += 30
    return {"engine": "fixture", "items": items}


class TestMergedAmountRows:
    """Regression: a label and its amount sharing ONE OCR region
    ("TOTAL: 1250") lost integer/thousands-grouped amounts because the
    merged-text fallback regex required a 2-digit fraction."""

    def test_merged_integer_total(self):
        result = extract(ocr_doc([
            [("MINIMART", 10)],
            [("123 Street", 10)],
            [("Invoice No: A-123", 10)],
            [("TOTAL: 1250", 10)],
        ]), source="t")
        assert result.invoice.total == Decimal(1250)

    def test_merged_grouped_total(self):
        result = extract(ocr_doc([
            [("MINIMART", 10)],
            [("123 Street", 10)],
            [("Invoice No: A-123", 10)],
            [("TOTAL: 1,234,567", 10)],
        ]), source="t")
        assert result.invoice.total == Decimal(1234567)

    def test_merged_item_row_with_integer_line_total(self):
        result = extract(ocr_doc([
            [("MINIMART", 10)],
            [("123 Street", 10)],
            [("Invoice No: A-123", 10)],
            [("CAFE", 10), ("2 x 10.000", 150), ("20.000", 330)],
            [("TOTAL: 20000", 10)],
        ]), source="t")
        assert [
            (i.description, i.quantity, i.unit_price, i.line_total)
            for i in result.invoice.line_items
        ] == [("CAFE", Decimal(2), Decimal(10000), Decimal(20000))]
        assert result.invoice.total == Decimal(20000)

    def test_space_grouped_integer_total(self):
        """Regression (review): the grouped branch rejected space
        separators, so "TOTAL: 1 234 567" degraded to the rightmost
        group ("567") instead of the full amount."""
        result = extract(ocr_doc([
            [("MINIMART", 10)],
            [("123 Street", 10)],
            [("Invoice No: A-123", 10)],
            [("TOTAL: 1 234 567", 10)],
        ]), source="t")
        assert result.invoice.total == Decimal(1234567)

    def test_stray_single_digit_cannot_win_rightmost(self):
        """Regression (review): bare integers matched a single stray
        digit, so "TOTAL: 97.20 0" resolved to 0; bare integers now
        need >= 2 digits in the merged fallback."""
        result = extract(ocr_doc([
            [("MINIMART", 10)],
            [("123 Street", 10)],
            [("Invoice No: A-123", 10)],
            [("TOTAL: 97.20 0", 10)],
        ]), source="t")
        assert result.invoice.total == Decimal("97.20")

    def test_malformed_run_still_yields_nothing(self):
        result = extract(ocr_doc([
            [("MINIMART", 10)],
            [("123 Street", 10)],
            [("Invoice No: A-123", 10)],
            [("TOTAL: 12.34.56.78", 10)],
        ]), source="t")
        assert result.invoice.total is None


class TestHeaderFieldRobustness:
    """Regression: optional label groups grabbed the next word on
    header lines ("Invoice Date: ..." -> "Date") and stopped the scan
    before the real value was reached."""

    def test_invoice_date_line_does_not_become_invoice_number(self):
        result = extract(ocr_doc([[("Invoice Date: 2026-10-25", 10)]]))
        assert result.invoice.invoice_number is None

    def test_receipt_from_line_does_not_become_invoice_number(self):
        result = extract(ocr_doc([[("RECEIPT FROM WALMART", 10)]]))
        assert result.invoice.invoice_number is None

    def test_real_number_after_blocked_label_line_is_found(self):
        result = extract(ocr_doc([
            [("Invoice Date: 2026-10-25", 10)],
            [("Invoice No: A-123", 10)],
        ]))
        assert result.invoice.invoice_number == "A-123"

    def test_dong_inside_a_word_is_not_currency(self):
        result = extract(ocr_doc([
            [("đơn giá đặt biệt", 10)],
            [("TOTAL 5.00 USD", 10)],
        ]))
        assert result.invoice.currency is None

    def test_standalone_dong_sign_is_currency(self):
        result = extract(ocr_doc([[("Gia: 5.000 đ", 10)]]))
        assert result.invoice.currency == "VND"


class TestShortHeaderlessReceipts:
    """D-16: short receipts without a table header must not lose their
    line items to a fixed 3-line letterhead skip. Headerless candidates
    need a product-like description, monetary evidence, no metadata
    markers, and a summary row below them to confirm the item region."""

    def test_two_line_receipt_recovers_one_item(self):
        result = extract(ocr_doc([
            [("COFFEE 25.000", 10)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [
            (item.description, item.quantity, item.unit_price, item.line_total)
            for item in invoice.line_items
        ] == [("COFFEE", None, None, money("25000"))]
        assert invoice.total == money("25000")
        assert invoice.validation_status == STATUS_REVIEW
        assert "line_items[0].quantity" not in result.provenance
        assert "line_items[0].unit_price" not in result.provenance
        assert result.provenance["line_items[0].line_total"].ocr_index == 0
        assert result.provenance["line_items[0].line_total"].text == "COFFEE 25.000"

    def test_merged_line_total_provenance_points_at_amount_token(self):
        result = extract(ocr_doc([
            [("COFFEE 25.000", 10), ("đ", 220)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [
            (item.description, item.line_total)
            for item in invoice.line_items
        ] == [("COFFEE", money("25000"))]
        provenance = result.provenance["line_items[0].line_total"]
        assert provenance.ocr_index == 0
        assert provenance.text == "COFFEE 25.000"

    def test_two_grouped_amounts_on_one_row_are_not_a_phone(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("ÁO THUN", 10), ("125.000", 150), ("250.000", 330)],
            [("TOTAL", 10), ("250.000", 330)],
        ]), source="short")
        invoice = result.invoice
        assert [
            (item.description, item.line_total)
            for item in invoice.line_items
        ] == [("ÁO THUN", money("250000"))]
        assert invoice.total == money("250000")
        assert invoice.validation_status == STATUS_OK

    def test_qty_row_with_unit_price_and_total_is_not_a_phone(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("TEA", 10), ("2 x 125.000", 150), ("250.000", 330)],
            [("TOTAL", 10), ("250.000", 330)],
        ]), source="short")
        invoice = result.invoice
        assert [
            (item.description, item.quantity, item.unit_price, item.line_total)
            for item in invoice.line_items
        ] == [("TEA", money("2"), money("125000"), money("250000"))]
        assert invoice.total == money("250000")
        assert invoice.validation_status == STATUS_OK

    def test_supplier_letterhead_stays_out_of_items(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("MILK 12.000", 10)],
            [("TOTAL 12.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert invoice.supplier == "MINI MART"
        assert [item.description for item in invoice.line_items] == ["MILK"]
        assert invoice.line_items[0].line_total == money("12000")
        assert invoice.total == money("12000")
        assert invoice.validation_status == STATUS_OK
        assert result.provenance["line_items[0].description"].ocr_index == 1

    def test_headerless_items_keep_reading_order_and_provenance(self):
        result = extract(ocr_doc([
            [("TEA 15.000", 10)],
            [("COOKIE 10.000", 10)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [
            (item.description, item.line_total)
            for item in invoice.line_items
        ] == [("TEA", money("15000")), ("COOKIE", money("10000"))]
        assert invoice.total == money("25000")
        assert result.provenance["line_items[0].line_total"].ocr_index == 0
        assert result.provenance["line_items[1].line_total"].ocr_index == 1

    def test_vietnamese_headerless_receipt_preserves_diacritics(self):
        result = extract(ocr_doc([
            [("CÀ PHÊ SỮA 25.000 đ", 10)],
            [("TRÀ ĐÀO 30.000 đ", 10)],
            [("TỔNG CỘNG 55.000 đ", 10)],
        ]), source="short")
        invoice = result.invoice
        assert invoice.currency == "VND"
        assert [item.description for item in invoice.line_items] == [
            "CÀ PHÊ SỮA",
            "TRÀ ĐÀO",
        ]
        assert [item.line_total for item in invoice.line_items] == [
            money("25000"),
            money("30000"),
        ]
        assert invoice.total == money("55000")
        assert invoice.validation_status == STATUS_REVIEW

    def test_attached_dong_sign_is_accepted_on_merged_item_rows(self):
        result = extract(ocr_doc([
            [("CÀ PHÊ SỮA 25.000đ", 10)],
            [("TỔNG CỘNG 25.000đ", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [
            (item.description, item.line_total)
            for item in invoice.line_items
        ] == [("CÀ PHÊ SỮA", money("25000"))]
        assert invoice.total == money("25000")

    @pytest.mark.parametrize("header_cells", [
        [("ITEM", 10), ("QTY x PRICE LINE TOTAL", 150)],
        [("SẢN PHẨM", 10), ("SỐ LƯỢNG ĐƠN GIÁ THÀNH TIỀN", 150)],
    ])
    def test_explicit_header_remains_authoritative(self, header_cells):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            header_cells,
            [("SOAP", 10), ("2 x 2.50", 150), ("5.00", 330)],
            [("TOTAL", 10), ("5.00", 330)],
        ]), source="header")
        invoice = result.invoice
        assert len(invoice.line_items) == 1
        item = invoice.line_items[0]
        assert (item.description, item.quantity, item.unit_price, item.line_total) == (
            "SOAP", money("2"), money("2.50"), money("5.00")
        )
        assert all("ITEM" not in i.description for i in invoice.line_items)
        assert all("SẢN PHẨM" not in i.description for i in invoice.line_items)
        assert invoice.total == money("5.00")
        assert invoice.validation_status == STATUS_OK

    def test_explicit_header_does_not_parse_metadata_rows_as_items(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("ITEM", 10), ("QTY x PRICE LINE TOTAL", 150)],
            [("SOAP", 10), ("2 x 2.50", 150), ("5.00", 330)],
            [("Tel: 0909 123 456", 10)],
            [("TOTAL", 10), ("5.00", 330)],
        ]), source="header")
        invoice = result.invoice
        assert [
            (item.description, item.line_total)
            for item in invoice.line_items
        ] == [("SOAP", money("5.00"))]
        assert invoice.total == money("5.00")
        assert invoice.validation_status == STATUS_OK

    def test_longer_headerless_receipt_recovers_items_before_old_cutoff(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("123 Demo Street, Sample City", 10)],
            [("Receipt #: 00001234", 10)],
            [("Date: 2026-10-25 Time: 10:30", 10)],
            [("SOAP 5.00", 10)],
            [("MILK 2.50", 10)],
            [("TOTAL 7.50", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["SOAP", "MILK"]
        assert [item.line_total for item in invoice.line_items] == [
            money("5.00"),
            money("2.50"),
        ]
        assert invoice.total == money("7.50")
        assert invoice.validation_status == STATUS_OK
        for item in invoice.line_items:
            assert "Date" not in item.description
            assert "Receipt" not in item.description

    @pytest.mark.parametrize("metadata_line", [
        "MINI MART",
        "123 Demo Street, Sample City",
        "123 Le Loi Street, Quan 1, 700000",
        "Store #123",
        "Store 123",
        "Cửa hàng số 5",
        "MINI MART 0909 123 456",
        "Tel: 090 123 4567",
        "Hotline: 1900 1234",
        "ĐT: 0909 123 456",
        "SĐT: (0909) 123-456",
        "Receipt #: 00001234",
        "Invoice No: A-123",
        "Số hóa đơn: 000123",
        "HÓA ĐƠN: 000123",
        "HĐ: 000123",
        "HĐ 000123",
        "No. 000123",
        "No. 1.234",
        "HD 123.456",
        "Số: 000123",
        "Phiếu 000123",
        "Mã KH 123.456",
        "123 Lê Lợi, Bến Thành, 700000",
        "Date: 2026-10-25 Time: 10:30",
        "25/10/2026 12:30",
        "Tax ID: 0123456789",
        "MST: 0312345678",
        "TXN 9876543210",
        "TXN 1,234,567",
        "Invoice No. 1.234",
        "Receipt No. 1.234",
        "Order 1.234",
        "Bill 000123",
        "Hotline 1900 1234",
        "Tel 090 123 4567",
        "ĐT 04 3825 1234",
        "Fax 3825 1234",
        "Hotline 3825 1234",
        "ĐT 3825 1234",
        "Phone 3825 1234",
        "Mobile 3825 1234",
        "LH: 1900 1234",
        "Mã giao dịch: 9876543210",
        "SUBTOTAL 25.000",
        "VAT 10%",
        "TOTAL 25.000",
        "CASH 25.000",
        "DEBIT CARD 25.000",
        "VISA CREDIT 25.000",
        "CHANGE 5.000",
        "DISCOUNT 2.000",
    ])
    def test_metadata_and_summary_rows_never_become_items(self, metadata_line):
        result = extract(ocr_doc([
            [(metadata_line, 10)],
            [("TOTAL 25.000", 10)],
        ]), source="metadata")
        assert result.invoice.line_items == []
        assert result.invoice.total == money("25000")

    @pytest.mark.parametrize("letterhead", [
        "TẠP HÓA 247",
        "MINI MART #247",
        "Circle K 123",
        "123 Lê Lợi 700000",
        "TẠP HÓA 247 ₫",
        "MINI MART #247 ₫",
    ])
    def test_letterhead_number_is_not_an_item(self, letterhead):
        result = extract(ocr_doc([
            [(letterhead, 10)],
            [("MILK 12.000", 10)],
            [("TOTAL 12.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["MILK"]
        assert invoice.total == money("12000")

    def test_store_name_with_number_is_not_an_item(self):
        result = extract(ocr_doc([
            [("MINI MART 24H", 10)],
            [("MILK 12.000", 10)],
            [("TOTAL 12.000", 10)],
        ]), source="short")
        assert [item.description for item in result.invoice.line_items] == ["MILK"]

    @pytest.mark.parametrize("product_line, description, amount", [
        ("PHONE CASE 25.000", "PHONE CASE", "25000"),
        ("PHONE CASE 1.250.000", "PHONE CASE", "1250000"),
        ("PHONE 25.000.000", "PHONE", "25000000"),
        ("ADDRESS BOOK 25.000", "ADDRESS BOOK", "25000"),
        ("STORE BRAND MILK 25.000", "STORE BRAND MILK", "25000"),
        ("Invoice Paper 25.000", "Invoice Paper", "25000"),
        ("Invoice A4 Paper 25.000", "Invoice A4 Paper", "25000"),
        ("TEL 40W LAMP 25.000", "TEL 40W LAMP", "25000"),
        ("FAX 500 SHEETS 25.000", "FAX 500 SHEETS", "25000"),
        ("ĐIỆN THOẠI 25.000", "ĐIỆN THOẠI", "25000"),
        ("BÀN ỦI 1800 25.000", "BÀN ỦI 1800", "25000"),
        ("LAPTOP 1900 25.000", "LAPTOP 1900", "25000"),
        ("STAFF PICK COFFEE 25.000", "STAFF PICK COFFEE", "25000"),
        ("CUSTOMER FAVORITE 25.000", "CUSTOMER FAVORITE", "25000"),
        ("1 KG ĐƯỜNG TRẮNG 20.000", "1 KG ĐƯỜNG TRẮNG", "20000"),
        ("2 BOWL PHO 25.000", "2 BOWL PHO", "25000"),
        ("2 ĐÔI QUẦN JEANS 500.000", "2 ĐÔI QUẦN JEANS", "500000"),
        ("2 PHỞ 100.000", "2 PHỞ", "100000"),
        ("2 ĐƯỜNG 20.000", "2 ĐƯỜNG", "20000"),
    ])
    def test_product_names_containing_metadata_words_survive(
        self, product_line, description, amount
    ):
        result = extract(ocr_doc([
            [(product_line, 10)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        assert [
            (item.description, item.line_total)
            for item in result.invoice.line_items
        ] == [(description, money(amount))]

    def test_tax_id_header_does_not_end_the_item_region(self):
        result = extract(ocr_doc([
            [("Tax ID: 0123456789", 10)],
            [("COFFEE 25.000", 10)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        assert [item.description for item in result.invoice.line_items] == ["COFFEE"]
        assert result.invoice.total == money("25000")
        assert result.invoice.tax is None

    def test_tax_id_row_is_not_read_as_monetary_tax(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("ITEM", 10), ("QTY x PRICE LINE TOTAL", 150)],
            [("SOAP", 10), ("2 x 2.50", 150), ("5.00", 330)],
            [("Tax ID: 0123456789", 10)],
            [("TOTAL", 10), ("5.00", 330)],
        ]), source="header")
        invoice = result.invoice
        assert invoice.tax is None
        assert invoice.total == money("5.00")
        assert invoice.validation_status == STATUS_OK

    def test_vietnamese_tax_id_row_is_not_read_as_monetary_tax(self):
        result = extract(ocr_doc([
            [("CÀ PHÊ SỮA 25.000", 10)],
            [("Mã số thuế: 0312345678", 10)],
            [("TỔNG CỘNG 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert invoice.tax is None
        assert invoice.total == money("25000")

    def test_card_payment_row_still_feeds_payment_validation(self):
        result = extract(ocr_doc([
            [("SOAP", 10), ("2 x 52.50", 150), ("105.00", 330)],
            [("TOTAL", 10), ("105.00", 330)],
            [("CARD PAYMENT", 10), ("110.00", 330)],
            [("CHANGE", 10), ("3.00", 330)],
        ]), source="short")
        invoice = result.invoice
        assert invoice.payment_amount == money("110.00")
        assert invoice.change_amount == money("3.00")
        assert invoice.validation_status == STATUS_INVALID
        assert any(
            "change_amount != payment_amount - total" in error
            for error in invoice.validation_errors
        )

    def test_document_id_with_separate_currency_token_is_not_an_item(self):
        result = extract(ocr_doc([
            [("Invoice No. 1.234", 10), ("đ", 220)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        assert result.invoice.line_items == []
        assert result.invoice.total == money("25000")

    def test_vietnamese_invoice_number_header_does_not_end_item_region(self):
        result = extract(ocr_doc([
            [("Số hóa đơn: 000123", 10)],
            [("CÀ PHÊ SỮA 25.000", 10)],
            [("TỔNG CỘNG 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert invoice.invoice_number == "000123"
        assert [item.description for item in invoice.line_items] == ["CÀ PHÊ SỮA"]
        assert invoice.total == money("25000")
        assert invoice.validation_status == STATUS_OK

    def test_payment_and_tax_rows_stay_out_of_items(self):
        result = extract(ocr_doc([
            [("TEA 15.000", 10)],
            [("SUBTOTAL 15.000", 10)],
            [("VAT 1.500", 10)],
            [("TOTAL 16.500", 10)],
            [("CASH 20.000", 10)],
            [("CHANGE 3.500", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["TEA"]
        assert invoice.subtotal == money("15000")
        assert invoice.tax == money("1500")
        assert invoice.total == money("16500")
        assert invoice.payment_amount == money("20000")
        assert invoice.change_amount == money("3500")
        assert invoice.validation_status == STATUS_REVIEW

    def test_payment_row_alone_closes_headerless_item_region(self):
        result = extract(ocr_doc([
            [("COFFEE 25.00", 10)],
            [("CARD PAYMENT 25.00", 10)],
        ]), source="payment-only")
        invoice = result.invoice
        assert [
            (item.description, item.quantity, item.unit_price, item.line_total)
            for item in invoice.line_items
        ] == [("COFFEE", None, None, money("25.00"))]
        assert invoice.payment_amount == money("25.00")
        assert invoice.total is None
        assert result.provenance["line_items[0].line_total"].ocr_index == 0
        assert invoice.validation_status == STATUS_REVIEW

    def test_payment_row_ends_headerless_region_before_later_rows(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("COFFEE 25.00", 10)],
            [("CARD PAYMENT 30.00", 10)],
            [("EXTRA 5.00", 10)],
            [("TOTAL 25.00", 10)],
        ]), source="payment-boundary")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["COFFEE"]
        assert invoice.line_items[0].line_total == money("25.00")
        assert invoice.payment_amount == money("30.00")
        assert invoice.total == money("25.00")
        assert result.provenance["line_items[0].description"].ocr_index == 1
        assert invoice.validation_status == STATUS_OK

    def test_payment_row_above_first_item_yields_no_items(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("CARD PAYMENT 25.00", 10)],
            [("COFFEE 25.00", 10)],
            [("TOTAL 25.00", 10)],
        ]), source="payment-first")
        invoice = result.invoice
        assert invoice.line_items == []
        assert invoice.payment_amount == money("25.00")
        assert invoice.total == money("25.00")

    def test_tax_id_between_items_does_not_close_the_region(self):
        result = extract(ocr_doc([
            [("COFFEE 25.00", 10)],
            [("Tax ID: 0123456789", 10)],
            [("COOKIE 10.00", 10)],
            [("TOTAL 35.00", 10)],
        ]), source="tax-id")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == [
            "COFFEE",
            "COOKIE",
        ]
        assert [item.line_total for item in invoice.line_items] == [
            money("25.00"),
            money("10.00"),
        ]
        assert invoice.tax is None
        assert invoice.total == money("35.00")
        assert invoice.validation_status == STATUS_REVIEW

    @pytest.mark.parametrize("metadata_cells", [
        [("HÓA ĐƠN VAT: 000123", 10)],
        [("TÊN CỬA HÀNG: TOTAL MART", 10)],
    ])
    def test_metadata_row_with_summary_keyword_does_not_close_region(
        self, metadata_cells
    ):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            metadata_cells,
            [("CÀ PHÊ SỮA 25.000", 10)],
            [("TỔNG CỘNG 25.000", 10)],
        ]), source="metadata-summary-keyword")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == [
            "CÀ PHÊ SỮA"
        ]
        assert invoice.total == money("25000")

    def test_explicit_header_payment_row_still_ends_item_region(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("ITEM", 10), ("QTY x PRICE LINE TOTAL", 150)],
            [("SOAP", 10), ("2 x 2.50", 150), ("5.00", 330)],
            [("CARD PAYMENT", 10), ("5.00", 330)],
            [("EXTRA", 10), ("5.00", 330)],
            [("TOTAL", 10), ("5.00", 330)],
        ]), source="header")
        invoice = result.invoice
        assert [
            (item.description, item.line_total)
            for item in invoice.line_items
        ] == [("SOAP", money("5.00"))]
        assert invoice.payment_amount == money("5.00")
        assert invoice.total == money("5.00")
        assert invoice.validation_status == STATUS_OK

    @pytest.mark.parametrize("payment_cells", [
        [("CARD PAYMENT 25.00", 10)],
        [("VISA PAYMENT 25.00", 10)],
        [("DEBIT CARD PAYMENT 25.00", 10)],
        [("CARD PAYMENT", 10), ("25.00", 330)],
        [("TIỀN MẶT 25.00", 10)],
        [("TIỀN KHÁCH ĐƯA", 10), ("25.00", 330)],
    ])
    def test_payment_summary_representations_close_the_region(
        self, payment_cells
    ):
        result = extract(ocr_doc([
            [("COFFEE 25.00", 10)],
            payment_cells,
        ]), source="payment")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["COFFEE"]
        assert invoice.line_items[0].line_total == money("25.00")
        assert invoice.payment_amount == money("25.00")
        assert invoice.total is None

    def test_recovered_items_participate_in_arithmetic_validation(self):
        result = extract(ocr_doc([
            [("COFFEE 25.000", 10)],
            [("SUBTOTAL 30.000", 10)],
            [("TOTAL 30.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.line_total for item in invoice.line_items] == [money("25000")]
        assert invoice.subtotal == money("30000")
        assert invoice.total == money("30000")
        assert invoice.validation_status == STATUS_INVALID
        assert any(
            "subtotal != sum(line_items.line_total)" in error
            for error in invoice.validation_errors
        )

    def test_vietnamese_summary_zone_excludes_payment_rows(self):
        result = extract(ocr_doc([
            [("CÀ PHÊ SỮA 25.000", 10)],
            [("TRÀ ĐÀO 30.000", 10)],
            [("TẠM TÍNH 55.000", 10)],
            [("THUẾ GTGT 5.500", 10)],
            [("TỔNG CỘNG 60.500", 10)],
            [("TIỀN KHÁCH ĐƯA 100.000", 10)],
            [("TIỀN THỪA 39.500", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == [
            "CÀ PHÊ SỮA",
            "TRÀ ĐÀO",
        ]
        assert invoice.subtotal == money("55000")
        assert invoice.tax == money("5500")
        assert invoice.total == money("60500")
        assert invoice.payment_amount == money("100000")
        assert invoice.change_amount == money("39500")
        assert invoice.validation_status == STATUS_REVIEW

    @pytest.mark.parametrize("phone_row", [
        "Fax 3825 1234",
        "ĐT 3825 1234",
        "Phone 3825 1234",
        "LH: 1900 1234",
    ])
    def test_unpunctuated_phone_row_is_not_a_description_continuation(
        self, phone_row
    ):
        result = extract(ocr_doc([
            [("CÀ PHÊ 25.000", 10)],
            [(phone_row, 10)],
            [("BÁNH MÌ 20.000", 10)],
            [("TỔNG CỘNG 45.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == [
            "CÀ PHÊ",
            "BÁNH MÌ",
        ]
        assert result.provenance["line_items[1].description"].ocr_index == 2
        assert invoice.total == money("45000")

    def test_metadata_between_items_is_not_a_description_continuation(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("TEA 15.000", 10)],
            [("Tel: 0909 123 456", 10)],
            [("COOKIE 10.000", 10)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["TEA", "COOKIE"]
        assert result.provenance["line_items[1].description"].ocr_index == 3

    def test_address_with_abbreviated_wards_is_not_an_item(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("TEA 15.000", 10)],
            [("123 Lê Lợi, P. Bến Thành, Q.1", 10)],
            [("COOKIE 10.000", 10)],
            [("TOTAL 25.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["TEA", "COOKIE"]
        assert result.provenance["line_items[1].description"].ocr_index == 3

    def test_multiline_description_after_first_item_keeps_provenance(self):
        result = extract(ocr_doc([
            [("MINI MART", 10)],
            [("TEA 15.000", 10)],
            [("SOAP", 10)],
            [("LAVENDER", 10)],
            [("5.000", 10)],
            [("TOTAL 20.000", 10)],
        ]), source="short")
        items = result.invoice.line_items
        assert [(item.description, item.line_total) for item in items] == [
            ("TEA", money("15000")),
            ("SOAP LAVENDER", money("5000")),
        ]
        assert result.provenance["line_items[1].description"].ocr_index == 2
        assert result.provenance["line_items[1].description"].text == "SOAP"
        assert result.provenance["line_items[1].line_total"].ocr_index == 4

    def test_numeric_letterhead_line_is_not_a_description_continuation(self):
        result = extract(ocr_doc([
            [("000123", 10)],
            [("TEA 15.000", 10)],
            [("TOTAL 15.000", 10)],
        ]), source="short")
        assert [item.description for item in result.invoice.line_items] == ["TEA"]

    def test_headerless_receipt_without_boxes_recovers_item(self):
        document = {"items": [
            {"text": "MINI MART"},
            {"text": "MILK 12.000"},
            {"text": "TOTAL 12.000"},
        ]}
        result = extract(document, source="short")
        invoice = result.invoice
        assert [item.description for item in invoice.line_items] == ["MILK"]
        assert invoice.total == money("12000")
        assert result.provenance["line_items[0].line_total"].box == []

    def test_single_headerless_amount_line_is_not_fabricated(self):
        result = extract(ocr_doc([[("COFFEE 25.000", 10)]]), source="short")
        invoice = result.invoice
        assert invoice.line_items == []
        assert invoice.total is None
        assert invoice.validation_status == STATUS_REVIEW
        assert any("ambiguous:" in error for error in invoice.validation_errors)

    def test_headerless_rows_without_summary_are_not_guessed(self):
        result = extract(ocr_doc([
            [("TEA 15.000", 10)],
            [("COOKIE 10.000", 10)],
        ]), source="short")
        invoice = result.invoice
        assert invoice.line_items == []
        assert invoice.total is None
        assert invoice.validation_status == STATUS_REVIEW
        assert any("ambiguous:" in error for error in invoice.validation_errors)

    def test_total_only_document_has_no_items(self):
        result = extract(ocr_doc([[("TOTAL 25.000", 10)]]), source="short")
        invoice = result.invoice
        assert invoice.line_items == []
        assert invoice.total == money("25000")
        assert invoice.validation_status == STATUS_REVIEW

    def test_summary_only_document_has_no_items(self):
        result = extract(ocr_doc([
            [("SUBTOTAL 20.000", 10)],
            [("VAT 2.000", 10)],
            [("TOTAL 22.000", 10)],
        ]), source="summary")
        invoice = result.invoice
        assert invoice.line_items == []
        assert invoice.subtotal == money("20000")
        assert invoice.tax == money("2000")
        assert invoice.total == money("22000")
        assert invoice.validation_status == STATUS_REVIEW

    def test_supplier_only_document_has_no_items(self):
        result = extract(ocr_doc([[("MINI MART", 10)]]), source="short")
        invoice = result.invoice
        assert invoice.supplier == "MINI MART"
        assert invoice.line_items == []
        assert invoice.validation_status == STATUS_REVIEW
