"""Evaluation manifest schema: predictions paired with ground truth.

Manifest format (JSON):

    {
      "task": "ocr" | "invoice" | "table",
      "documents": [
        {"id": "doc-1", "prediction": "outputs/a.json",
         "ground_truth": "data/eval/ocr/a.truth.json"}
      ]
    }

Paths are resolved relative to the manifest file's directory (or stay
absolute). Validation is strict so a broken manifest fails loudly
instead of producing misleading metrics.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

KNOWN_TASKS = ("ocr", "invoice", "table")
KNOWN_PROVENANCE = ("synthetic", "real", "unknown")


class ManifestError(ValueError):
    """Raised when an evaluation manifest is missing or malformed."""


@dataclass
class ManifestEntry:
    id: str
    prediction: Path
    ground_truth: Path


@dataclass
class Manifest:
    task: str
    entries: list[ManifestEntry] = field(default_factory=list)
    path: Path | None = None
    # Explicit dataset provenance; "unknown" unless the manifest declares
    # otherwise. Nothing is ever classified as real automatically.
    provenance: str = "unknown"


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a manifest, resolving entry paths."""
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Malformed JSON manifest '{manifest_path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"Manifest must be a JSON object: '{manifest_path}'")

    task = raw.get("task")
    if task not in KNOWN_TASKS:
        raise ManifestError(
            f"Manifest task must be one of {KNOWN_TASKS}, got {task!r}"
        )
    provenance = raw.get("provenance", "unknown")
    if provenance not in KNOWN_PROVENANCE:
        raise ManifestError(
            f"Manifest provenance must be one of {KNOWN_PROVENANCE} "
            f"(defaults to 'unknown'), got {provenance!r}"
        )
    documents = raw.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ManifestError(
            f"Manifest 'documents' must be a non-empty list: '{manifest_path}'"
        )

    entries: list[ManifestEntry] = []
    seen_ids: set[str] = set()
    for position, entry in enumerate(documents):
        if not isinstance(entry, dict):
            raise ManifestError(f"documents[{position}] must be an object")
        document_id = entry.get("id")
        prediction = entry.get("prediction")
        ground_truth = entry.get("ground_truth")
        for name, value in (
            ("id", document_id), ("prediction", prediction), ("ground_truth", ground_truth)
        ):
            if not isinstance(value, str) or not value.strip():
                raise ManifestError(
                    f"documents[{position}].{name} must be a non-empty string"
                )
        if document_id in seen_ids:
            raise ManifestError(f"Duplicate document id {document_id!r}")
        seen_ids.add(document_id)
        entries.append(
            ManifestEntry(
                id=document_id,
                prediction=_resolve(manifest_path.parent, prediction),
                ground_truth=_resolve(manifest_path.parent, ground_truth),
            )
        )
    return Manifest(task=task, entries=entries, path=manifest_path,
                    provenance=provenance)


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate)
