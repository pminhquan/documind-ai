"""Typed models for receipt/invoice extraction results.

Financial values are stored as :class:`decimal.Decimal` (never float) so
that printed amounts survive parsing and arithmetic without binary
rounding artifacts. When serialized to JSON they become strings that
preserve the printed scale (``Decimal("5.00") -> "5.00"``).
"""

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

STATUS_OK = "ok"
STATUS_REVIEW = "review_required"
STATUS_INVALID = "invalid"


@dataclass(frozen=True)
class Provenance:
    """Links an extracted field back to its source OCR text region."""

    ocr_index: int
    text: str
    box: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ocr_index": self.ocr_index, "text": self.text, "box": self.box}


@dataclass
class LineItem:
    """One purchased line: quantity x unit_price == line_total."""

    description: str = ""
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


@dataclass
class Invoice:
    supplier: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    line_items: list[LineItem] = field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    discount: Decimal | None = None
    total: Decimal | None = None
    payment_amount: Decimal | None = None
    change_amount: Decimal | None = None
    validation_status: str = STATUS_OK
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Invoice plus provenance, produced from one OCR JSON document."""

    source: str = ""
    invoice: Invoice = field(default_factory=Invoice)
    provenance: dict[str, Provenance] = field(default_factory=dict)

    def to_dict(self) -> dict:
        def money(value: Decimal | None) -> str | None:
            return str(value) if value is not None else None

        inv = self.invoice
        return {
            "source": self.source,
            "invoice": {
                "supplier": inv.supplier,
                "invoice_number": inv.invoice_number,
                "invoice_date": (
                    inv.invoice_date.isoformat() if inv.invoice_date else None
                ),
                "currency": inv.currency,
                "line_items": [
                    {
                        "description": item.description,
                        "quantity": money(item.quantity),
                        "unit_price": money(item.unit_price),
                        "line_total": money(item.line_total),
                    }
                    for item in inv.line_items
                ],
                "subtotal": money(inv.subtotal),
                "tax": money(inv.tax),
                "discount": money(inv.discount),
                "total": money(inv.total),
                "payment_amount": money(inv.payment_amount),
                "change_amount": money(inv.change_amount),
                "validation_status": inv.validation_status,
                "validation_errors": list(inv.validation_errors),
            },
            "provenance": {
                path: prov.to_dict() for path, prov in self.provenance.items()
            },
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
