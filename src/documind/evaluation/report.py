"""Readable Markdown report generation for evaluation summaries."""

from .invoice_eval import SCALAR_FIELDS

WORST_DOCUMENTS = 3


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _worst(documents: list[dict], rate_key: str,
           highest_is_worst: bool = False) -> list[dict]:
    """Documents sorted worst-first; None metrics drop out.

    For CER a higher rate is worse; for accuracy/agreement a lower rate
    is worse.
    """
    rated = [doc for doc in documents if doc.get(rate_key) is not None]
    return sorted(rated, key=lambda doc: doc[rate_key], reverse=highest_is_worst)


def _provenance_lines(summary: dict) -> list[str]:
    provenance = summary.get("dataset", {}).get("provenance", "unknown")
    notes = {
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
    return [f"Dataset provenance: {provenance}", "",
            notes.get(provenance, notes["unknown"]), ""]


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
        "### Worst-performing documents (highest CER)",
        "",
    ]
    for document in _worst(summary["documents"], "cer",
                           highest_is_worst=True)[:WORST_DOCUMENTS]:
        lines.append(
            f"- **{document['id']}**: CER {_fmt(document['cer'])} "
            f"({document['cer_edits']}/{document['cer_reference_length']} edits)"
        )
    if not summary["documents"]:
        lines.append("- none")
    lines += [
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
        "| Document | Field accuracy | Matched | Missing | Extra | Incorrect "
        "| Item P | Item R | Item F1 | Items matched (expected/predicted) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for document in summary["documents"]:
        doc_summary = document["summary"]
        line_items = document["line_items"]
        lines.append(
            f"| {document['id']} | {_fmt(doc_summary['accuracy'])} | "
            f"{doc_summary['matched']} | {doc_summary['missing']} | "
            f"{doc_summary['extra']} | {doc_summary['incorrect']} | "
            f"{_fmt(line_items.get('item_precision'))} | "
            f"{_fmt(line_items.get('item_recall'))} | "
            f"{_fmt(line_items.get('item_f1'))} | "
            f"{line_items['items_matched']} "
            f"({line_items['expected_items']}/{line_items['predicted_items']}) |"
        )
    lines += [
        "",
        f"**Micro field accuracy:** {_fmt(aggregate['micro_field_accuracy'])} "
        f"({aggregate['fields_matched']}/{aggregate['fields_applicable']}); "
        f"**macro:** {_fmt(aggregate['macro_field_accuracy'])}; "
        f"item field accuracy (matched pairs): "
        f"{_fmt(aggregate['item_field_accuracy'])} "
        f"({aggregate['item_field_correct']}/{aggregate['item_field_total']}); "
        f"item precision {_fmt(aggregate['item_precision'])} / recall "
        f"{_fmt(aggregate['item_recall'])} / F1 {_fmt(aggregate['item_f1'])}; "
        f"missing line items {aggregate['missing_line_items']}, "
        f"extra line items {aggregate['extra_line_items']}.",
        "",
        f"Evaluated fields: {', '.join(SCALAR_FIELDS)} + line_items.",
        "",
        "### Worst-performing documents (lowest field accuracy)",
        "",
    ]
    for document in _worst(
        [{"id": doc["id"], "accuracy": doc["summary"]["accuracy"]}
         for doc in summary["documents"]],
        "accuracy",
    )[:WORST_DOCUMENTS]:
        lines.append(
            f"- **{document['id']}**: field accuracy {_fmt(document['accuracy'])}"
        )
    if not summary["documents"]:
        lines.append("- none")
    lines += [
        "",
        "### Most problematic fields (documents with issues)",
        "",
    ]
    field_issue_counts: dict[str, int] = {}
    for document in summary["documents"]:
        for name, outcome in document["fields"].items():
            if outcome["status"] in ("missing", "extra", "incorrect"):
                field_issue_counts[name] = field_issue_counts.get(name, 0) + 1
    if field_issue_counts:
        for name, count in sorted(field_issue_counts.items(),
                                  key=lambda item: (-item[1], item[0]))[:WORST_DOCUMENTS]:
            lines.append(f"- **{name}**: issues in {count} document(s)")
    else:
        lines.append("- none")
    lines += [
        "",
        "### Field issues per document",
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
    return lines


def _table_report(summary: dict) -> list[str]:
    aggregate = summary["aggregate"]
    lines = [
        "| Document | Expected | Predicted | Missed | Extra | Structure OK "
        "| Cells matched | Exact agreement | Prediction precision | Strict agreement |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for document in summary["documents"]:
        metrics = document["document_metrics"]
        structure_ok = (
            all(c["structure_ok"] for c in document["comparisons"])
            and document["tables_missed"] == 0 and document["tables_extra"] == 0
        )
        lines.append(
            f"| {document['id']} | {document['tables_expected']} | "
            f"{document['tables_predicted']} | {document['tables_missed']} | "
            f"{document['tables_extra']} | "
            f"{'yes' if structure_ok else 'no'} | "
            f"{metrics['cells_matched']} / {metrics['cells_expected']} | "
            f"{_fmt(aggregate_cell_rate(document))} | "
            f"{_fmt(metrics['prediction_precision'])} | "
            f"{_fmt(metrics['strict_cell_agreement'])} |"
        )
    lines += [
        "",
        f"**Aggregate:** cell exact agreement {_fmt(aggregate['cell_exact_agreement'])} "
        f"({aggregate['cells_matched']}/{aggregate['cells_total']} expected "
        f"reference cells — extra predictions do not enter this denominator); "
        f"**prediction precision** {_fmt(aggregate['prediction_precision'])}; "
        f"**strict cell agreement** {_fmt(aggregate['strict_cell_agreement'])}; "
        f"non-empty agreement {_fmt(aggregate['non_empty_agreement'])}; "
        f"empty-cell preservation {_fmt(aggregate['empty_cell_preservation'])}; "
        f"tables expected {aggregate['tables_expected']}, predicted "
        f"{aggregate['tables_predicted']}, missed {aggregate['tables_missed']}, "
        f"extra {aggregate['tables_extra']}; structure-ok documents "
        f"{aggregate['structure_ok_documents']}/{len(summary['documents'])}.",
        "",
        f"Missing cells {aggregate['missing_cells']}, extra cells "
        f"{aggregate['extra_cells']} (including out-of-shape, duplicate, and "
        f"invalid-coordinate predictions), incorrect cells "
        f"{aggregate['incorrect_cells']}.",
        "",
        "### Worst-performing documents (lowest strict cell agreement)",
        "",
    ]
    for document in _worst(
        [{"id": doc["id"],
          "strict": doc["document_metrics"]["strict_cell_agreement"]}
         for doc in summary["documents"]],
        "strict",
    )[:WORST_DOCUMENTS]:
        lines.append(
            f"- **{document['id']}**: strict cell agreement "
            f"{_fmt(document['strict'])}"
        )
    if not summary["documents"]:
        lines.append("- none")
    return lines


def aggregate_cell_rate(document: dict) -> float | None:
    total = document["document_metrics"]["cells_expected"]
    matched = document["document_metrics"]["cells_matched"]
    return (matched / total) if total else None


def render_markdown(summary: dict) -> str:
    task = summary["task"]
    conventions = "\n".join(
        f"- **{key.replace('_', ' ')}**: {value}"
        for key, value in summary.get("conventions", {}).items()
    )
    body = {"ocr": _ocr_report, "invoice": _invoice_report,
            "table": _table_report}[task](summary)
    return "\n".join([
        f"# Evaluation report — task: {task}",
        "",
        *_provenance_lines(summary),
        "## Per-document results",
        "",
        *body,
        "",
        "## Conventions",
        "",
        conventions,
        "",
    ])
