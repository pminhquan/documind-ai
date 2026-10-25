"""Arithmetic consistency validation for extracted invoices.

Every check runs only when all operands were actually extracted; missing
values never produce errors (absence is not an inconsistency).
"""

from decimal import Decimal

from .models import Invoice, STATUS_INVALID, STATUS_OK, STATUS_REVIEW

AMBIGUITY_PREFIX = "ambiguous:"


def validate_invoice(invoice: Invoice) -> list[str]:
    """Return arithmetic-consistency error strings (empty when consistent)."""
    errors: list[str] = []

    for position, item in enumerate(invoice.line_items):
        if (
            item.quantity is not None
            and item.unit_price is not None
            and item.line_total is not None
            and item.quantity * item.unit_price != item.line_total
        ):
            errors.append(
                f"line_items[{position}]: quantity x unit_price != line_total"
            )

    line_totals = [
        item.line_total
        for item in invoice.line_items
        if item.line_total is not None
    ]
    if invoice.subtotal is not None and line_totals:
        if sum(line_totals, Decimal("0")) != invoice.subtotal:
            errors.append("subtotal != sum(line_items.line_total)")

    if invoice.total is not None and invoice.subtotal is not None:
        if invoice.tax is not None or invoice.discount is not None:
            expected = invoice.subtotal + (invoice.tax or Decimal("0")) - (
                invoice.discount or Decimal("0")
            )
            if invoice.total != expected:
                errors.append("total != subtotal + tax - discount")
        elif invoice.total != invoice.subtotal:
            errors.append("total != subtotal (no tax/discount extracted)")

    if (
        invoice.payment_amount is not None
        and invoice.change_amount is not None
        and invoice.total is not None
        and invoice.change_amount
        != invoice.payment_amount - invoice.total
    ):
        errors.append("change_amount != payment_amount - total")

    return errors


def apply_validation(invoice: Invoice, ambiguities: list[str] | None = None) -> None:
    """Compute ``validation_status`` and ``validation_errors`` in place.

    ``ambiguities`` are extractor notes (prefixed ``ambiguous:``) about
    input that could plausibly map to several fields. Arithmetic errors
    mark the invoice invalid; ambiguities alone mark it review_required.
    """
    arithmetic_errors = validate_invoice(invoice)
    notes = [f"{AMBIGUITY_PREFIX} {note}" for note in (ambiguities or [])]
    invoice.validation_errors = arithmetic_errors + notes

    if arithmetic_errors:
        invoice.validation_status = STATUS_INVALID
    elif notes:
        invoice.validation_status = STATUS_REVIEW
    else:
        invoice.validation_status = STATUS_OK
