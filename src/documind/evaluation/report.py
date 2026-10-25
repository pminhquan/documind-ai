"""Readable Markdown report generation for evaluation summaries."""

from .invoice_eval import SCALAR_FIELDS


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _ocr_report(summary: dict) -> list[str]:
    aggregate = summary["aggregate"]
    lines = [
        "| Document | CER | WER | Substitutions | Insertions | Deletions "
        "| CER edits / ref chars |",
        "|---|---|---|---|---|---|---|",
    ]
    for document in summary["documents"]:
        counts = document.get("operation_counts", {})
        lines.append(
            f"| {document['id']} | {_fmt(document['cer'])} | "
            f"{_fmt(document['wer'])} | {counts.get('substitute', 0)} | "
            f"{counts.get('insert', 0)} | {counts.get('delete', 0)} | "
            f"{document['cer_edits']} / {document['cer_reference_length']} |"
        )
    lines += [
        "",
        f"**Micro aggregate:** CER {_fmt(aggregate['cer'])}, "
        f"WER {_fmt(aggregate['wer'])} "
        f"({aggregate['cer_total_edits']} char edits over "
        f"{aggregate['cer_total_reference_chars']} reference characters; "
        f"{aggregate['wer_total_edits']} word edits over "
        f"{aggregate['wer_total_reference_words']} reference words).",
        "",
        f"**Edit mix:** substitutions: {aggregate.get('substitutions', 0)}, "
        f"insertions: {aggregate.get('insertions', 0)}, "
        f"deletions: {aggregate.get('deletions', 0)}.",
        "",
        "### Error examples (first per document)",
        "",
    ]
    for document in summary["documents"]:
        lines.append(f"- **{document['id']}**")
        for operation in document["examples"]:
            lines.append(
                f"  - {operation['op']} at ref position {operation['position']}: "
                f"reference {operation['reference']!r} -> hypothesis "
                f"{operation['hypothesis']!r}"
            )
        if not document["examples"]:
            lines.append("  - none")
    return lines


def _invoice_report(summary: dict) -> list[str]:
    aggregate = summary["aggregate"]
    lines = [
        "| Document | Field accuracy | Matched | Missing | Extra | Incorrect | "
        "Items matched (expected/predicted) |",
        "|---|---|---|---|---|---|---|",
    ]
    for document in summary["documents"]:
        doc_summary = document["summary"]
        line_items = document["line_items"]
        lines.append(
            f"| {document['id']} | {_fmt(doc_summary['accuracy'])} | "
            f"{doc_summary['matched']} | {doc_summary['missing']} | "
            f"{doc_summary['extra']} | {doc_summary['incorrect']} | "
            f"{line_items['items_matched']} "
            f"({line_items['expected_items']}/{line_items['predicted_items']}) |"
        )
    lines += [
        "",
        "### Field issues (missing / extra / incorrect)",
        "",
    ]
    for document in summary["documents"]:
        issues = [
            f"{name}: {outcome['status']} (expected {outcome['expected']!r}, "
            f"predicted {outcome['predicted']!r})"
            for name, outcome in document["fields"].items()
            if outcome["status"] in ("missing", "extra", "incorrect")
        ]
        lines.append(f"- **{document['id']}**: " + ("; ".join(issues) if issues else "none"))
    lines += [
        "",
        f"**Micro field accuracy:** {_fmt(aggregate['micro_field_accuracy'])} "
        f"({aggregate['fields_matched']}/{aggregate['fields_applicable']}); "
        f"**macro:** {_fmt(aggregate['macro_field_accuracy'])}; "
        f"item field accuracy: {_fmt(aggregate['item_field_accuracy'])} "
        f"({aggregate['item_field_correct']}/{aggregate['item_field_total']}); "
        f"missing line items {aggregate['missing_line_items']}, "
        f"extra line items {aggregate['extra_line_items']}.",
        "",
        f"Evaluated fields: {', '.join(SCALAR_FIELDS)} + line_items.",
    ]
    return lines


def _table_report(summary: dict) -> list[str]:
    aggregate = summary["aggregate"]
    lines = [
        "| Document | Expected | Predicted | Missed | Extra | Structure OK | "
        "Cells matched | Exact agreement |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for document in summary["documents"]:
        lines.append(
            f"| {document['id']} | {document['tables_expected']} | "
            f"{document['tables_predicted']} | {document['tables_missed']} | "
            f"{document['tables_extra']} | "
            f"{'yes' if all(c['structure_ok'] for c in document['comparisons']) and document['tables_missed'] == 0 else 'no'} | "
            f"{sum(c['cells_matched'] for c in document['comparisons'])} / "
            f"{sum(c['cells_total'] for c in document['comparisons'])} | "
            f"{_fmt(aggregate_cell_rate(document))} |"
        )
    lines += [
        "",
        f"**Aggregate:** cell exact agreement {_fmt(aggregate['cell_exact_agreement'])} "
        f"({aggregate['cells_matched']}/{aggregate['cells_total']}); "
        f"non-empty agreement {_fmt(aggregate['non_empty_agreement'])}; "
        f"empty-cell preservation {_fmt(aggregate['empty_cell_preservation'])}; "
        f"tables expected {aggregate['tables_expected']}, predicted "
        f"{aggregate['tables_predicted']}, missed {aggregate['tables_missed']}, "
        f"extra {aggregate['tables_extra']}; structure-ok documents "
        f"{aggregate['structure_ok_documents']}/{len(summary['documents'])}.",
        "",
        f"Missing cells {aggregate['missing_cells']}, extra cells "
        f"{aggregate['extra_cells']}, incorrect cells "
        f"{aggregate['incorrect_cells']}.",
    ]
    return lines


def aggregate_cell_rate(document: dict) -> float | None:
    total = sum(c["cells_total"] for c in document["comparisons"])
    matched = sum(c["cells_matched"] for c in document["comparisons"])
    return (matched / total) if total else None


def render_markdown(summary: dict) -> str:
    task = summary["task"]
    provenance = summary.get("dataset", {}).get("provenance", "unknown")
    provenance_notes = {
        "synthetic": (
            "Dataset provenance: **synthetic** — results demonstrate "
            "pipeline correctness on clean generated inputs and are not "
            "real-world accuracy."
        ),
        "real": (
            "Dataset provenance: **real** — results apply to the labeled "
            "documents in this dataset only; see the dataset's provenance "
            "notes for scope and collection caveats."
        ),
        "unknown": (
            "Dataset provenance: **unknown** — interpret with caution; do "
            "not treat these numbers as real-world accuracy."
        ),
    }
    conventions = "\n".join(
        f"- **{key.replace('_', ' ')}**: {value}"
        for key, value in summary.get("conventions", {}).items()
    )
    body = {"ocr": _ocr_report, "invoice": _invoice_report,
            "table": _table_report}[task](summary)
    return "\n".join([
        f"# Evaluation report — task: {task}",
        "",
        f"Dataset provenance: {provenance}",
        "",
        provenance_notes.get(provenance, provenance_notes["unknown"]),
        "",
        "## Per-document results",
        "",
        *body,
        "",
        "## Conventions",
        "",
        conventions,
        "",
    ])
