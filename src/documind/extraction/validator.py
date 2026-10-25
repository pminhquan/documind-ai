"""Arithmetic consistency and completeness validation for invoices.

Completeness and arithmetic consistency are judged separately:

- ``ok``: sufficiently complete required fields, with no detected
  arithmetic inconsistency or ambiguity.
- ``review_required``: critical information is missing, incomplete, or
  ambiguous (``incomplete:`` / ``ambiguous:`` notes).
- ``invalid``: an arithmetic inconsistency is actually demonstrated by
  sufficient extracted operands.

Sufficiently complete (M2 baseline): at least one monetary anchor — a
grand total, a subtotal, or a line item carrying a line_total — AND at
least one identification field (supplier, invoice number, or invoice
date). Optional fields (tax, discount, payment, change) never affect
completeness when absent from the document.

Every arithmetic check runs only when ALL of its operands were
extracted; missing values never produce errors (absence is not an
inconsistency). The subtotal check additionally requires every
extracted line item to carry a line_total, so a partially extracted
item list is never reported as a subtotal mismatch.
"""

from decimal import Decimal

from .models import STATUS_INVALID, STATUS_OK, STATUS_REVIEW, Invoice

AMBIGUITY_PREFIX = "ambiguous:"
INCOMPLETE_PREFIX = "incomplete:"


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

    if invoice.subtotal is not None and invoice.line_items:
        line_totals = [item.line_total for item in invoice.line_items]
        if all(total is not None for total in line_totals):
            if sum(line_totals, Decimal(0)) != invoice.subtotal:
                errors.append("subtotal != sum(line_items.line_total)")

    if invoice.total is not None and invoice.subtotal is not None:
        if invoice.tax is not None or invoice.discount is not None:
            expected = invoice.subtotal + (invoice.tax or Decimal(0)) - (
                invoice.discount or Decimal(0)
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


def incompleteness_notes(invoice: Invoice) -> list[str]:
    """Return ``incomplete:`` notes when the extraction is not sufficiently
    complete for the M2 baseline (see module docstring)."""
    notes: list[str] = []

    monetary_anchor = (
        invoice.total is not None
        or invoice.subtotal is not None
        or any(item.line_total is not None for item in invoice.line_items)
    )
    identification = (
        invoice.supplier is not None
        or invoice.invoice_number is not None
        or invoice.invoice_date is not None
    )

    if not monetary_anchor:
        notes.append(
            f"{INCOMPLETE_PREFIX} no monetary anchor extracted "
            "(no total, subtotal, or line-item amount)"
        )
    if not identification:
        notes.append(
            f"{INCOMPLETE_PREFIX} none of supplier, invoice number, "
            "or invoice date identified"
        )
    return notes


def apply_validation(invoice: Invoice, ambiguities: list[str] | None = None) -> None:
    """Compute ``validation_status`` and ``validation_errors`` in place.

    Arithmetic errors mark the invoice invalid; ambiguity and
    incompleteness notes mark it review_required.
    """
    arithmetic_errors = validate_invoice(invoice)
    ambiguity_notes = [f"{AMBIGUITY_PREFIX} {note}" for note in (ambiguities or [])]
    completeness_notes = incompleteness_notes(invoice)
    invoice.validation_errors = arithmetic_errors + ambiguity_notes + completeness_notes

    if arithmetic_errors:
        invoice.validation_status = STATUS_INVALID
    elif ambiguity_notes or completeness_notes:
        invoice.validation_status = STATUS_REVIEW
    else:
        invoice.validation_status = STATUS_OK
