---
name: privacy-and-upload-safety
description: Work on dataset onboarding, upload handling, or any feature touching user-provided documents — use when handling file inputs, temp storage, export paths, or personal data.
---

# Privacy and upload safety

## Purpose

Protect user documents: nothing private enters Git, uploads are treated
as untrusted, ground truth is never machine-generated.

## When to use

- Changing `src/documind/dataset.py`, `dataset_cli.py`, any upload or
  export endpoint, or anything reading user-provided files.
- Adding temp-file handling, filename handling, or archive/ZIP writing.

## Relevant modules

- `src/documind/dataset.py` (`add_document` confirmation gate)
- `src/documind/ocr/validation.py` (size/extension checks)
- `src/documind/tables/exporters.py` (formula-injection policy)
- `docs/dataset-annotation-guide.md` (redaction checklist, licensing)
- `.gitignore` (`data/eval/real/` fully ignored)

## Non-negotiable rules

- Never commit anything under `data/eval/real/`, `data/raw/`, or any
  user-provided document.
- Validate uploads: size limit, extension allowlist, decoded-content
  check; safe temp locations with cleanup on every path (including
  failures); no path traversal; no execution of uploaded content.
- Sanitize export filenames, ZIP entries, and worksheet names; keep the
  CSV formula-injection policy intact.
- Ground truth comes from humans, never from model predictions.

## Workflow

1. Write the failing test for the unsafe path first (oversize, wrong
   extension, traversal attempt, malformed content).
2. Fix at the boundary (validation layer), not ad hoc at call sites.
3. Confirm the git-ignored status of any new local-data directory.

## Verification

```
python scripts/verify.py
git check-ignore data/eval/real/README.md && echo ignored
pytest tests/test_dataset.py tests/test_tables_export.py -q
```

## Failure and rollback criteria

- Any change that widens accepted file types/sizes without a documented
  reason, or that could commit private data, must be reverted.
- Silent exception swallowing around file handling is a defect.
