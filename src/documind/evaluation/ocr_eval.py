"""OCR evaluation: CER/WER of recognized text against reference text.

Predictions are saved ``documind-ocr`` JSON documents (``full_text``);
ground truth is ``{"id": ..., "reference_text": "..."}``. No OCR model
is run and model confidence is never used.
"""

import json
from pathlib import Path

from .text_metrics import (
    TextMetricResult,
    edit_operations,
    error_rate,
    micro_aggregate,
    normalize_text,
)

MAX_EXAMPLES = 5


def evaluate_document(prediction_path: Path, ground_truth_path: Path,
                      *, casefold: bool = True,
                      collapse_whitespace: bool = True) -> dict:
    reference = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    if not isinstance(reference, dict) or "reference_text" not in reference:
        raise ValueError(f"OCR ground truth needs 'reference_text': {ground_truth_path}")
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    if not isinstance(prediction, dict) or "full_text" not in prediction:
        raise ValueError(f"OCR prediction needs 'full_text': {prediction_path}")

    reference_norm = normalize_text(
        str(reference["reference_text"]), casefold=casefold,
        collapse_whitespace=collapse_whitespace,
    )
    hypothesis_norm = normalize_text(
        str(prediction["full_text"]), casefold=casefold,
        collapse_whitespace=collapse_whitespace,
    )
    result: TextMetricResult = error_rate(
        str(reference["reference_text"]), str(prediction["full_text"]),
        unit="chars", casefold=casefold, collapse_whitespace=collapse_whitespace,
    )
    words: TextMetricResult = error_rate(
        str(reference["reference_text"]), str(prediction["full_text"]),
        unit="words", casefold=casefold, collapse_whitespace=collapse_whitespace,
    )
    operations = edit_operations(reference_norm, hypothesis_norm)
    counts = {"substitute": 0, "insert": 0, "delete": 0}
    for operation in operations:
        counts[operation["op"]] += 1
    return {
        "cer": result,
        "wer": words,
        "operation_counts": counts,
        "examples": operations[:MAX_EXAMPLES],
    }


def evaluate_manifest(manifest, *, casefold: bool = True,
                      collapse_whitespace: bool = True) -> dict:
    """Evaluate every manifest entry and build the aggregate summary."""
    documents = []
    results = []
    word_results = []
    total_counts = {"substitute": 0, "insert": 0, "delete": 0}
    for entry in manifest.entries:
        outcome = evaluate_document(
            entry.prediction, entry.ground_truth,
            casefold=casefold, collapse_whitespace=collapse_whitespace,
        )
        cer: TextMetricResult = outcome["cer"]
        wer: TextMetricResult = outcome["wer"]
        results.append(cer)
        word_results.append(wer)
        for kind, count in outcome["operation_counts"].items():
            total_counts[kind] += count
        documents.append({
            "id": entry.id,
            "cer": cer.error_rate,
            "cer_edits": cer.edits,
            "cer_reference_length": cer.reference_length,
            "wer": wer.error_rate,
            "wer_edits": wer.edits,
            "wer_reference_length": wer.reference_length,
            "operation_counts": outcome["operation_counts"],
            "examples": outcome["examples"],
        })

    cer_aggregate = micro_aggregate(results)
    wer_aggregate = micro_aggregate(word_results)
    return {
        "task": "ocr",
        "documents": documents,
        "aggregate": {
            "cer": cer_aggregate["error_rate"],
            "cer_total_edits": cer_aggregate["total_edits"],
            "cer_total_reference_chars": cer_aggregate["total_reference_units"],
            "wer": wer_aggregate["error_rate"],
            "wer_total_edits": wer_aggregate["total_edits"],
            "wer_total_reference_words": wer_aggregate["total_reference_units"],
            "substitutions": total_counts["substitute"],
            "insertions": total_counts["insert"],
            "deletions": total_counts["delete"],
        },
        "conventions": {
            "normalization": "NFKC; casefold and whitespace collapse configurable",
            "empty_reference": "both empty -> 0.0; empty reference only -> 1.0",
            "aggregation": "micro: total edits / total reference length",
            "confidence": "model confidence is never used as an accuracy metric",
        },
    }
