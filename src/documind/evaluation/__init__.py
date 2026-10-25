"""Reproducible evaluation framework (M4A).

Metrics for the three existing pipelines (OCR text, invoice extraction,
table recognition), driven by manifests pairing saved prediction files
with ground-truth annotations. No model inference; no confidence-based
accuracy.
"""

from .manifest import KNOWN_TASKS, Manifest, ManifestEntry, ManifestError, load_manifest
from .text_metrics import (
    TextMetricResult,
    edit_operations,
    error_rate,
    levenshtein_distance,
    micro_aggregate,
    normalize_text,
)

__all__ = [
    "KNOWN_TASKS",
    "Manifest",
    "ManifestEntry",
    "ManifestError",
    "load_manifest",
    "TextMetricResult",
    "edit_operations",
    "error_rate",
    "levenshtein_distance",
    "micro_aggregate",
    "normalize_text",
]
