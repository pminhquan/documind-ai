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
