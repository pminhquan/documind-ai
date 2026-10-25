---
name: performance-benchmark
description: Measure or optimize DocuMind runtime performance (OCR init/inference, batch, web endpoints) — use before and during any performance-motivated change.
---

# Performance benchmark

## Purpose

Ensure performance claims are measured, reproducible, and honestly
reported; prevent unverified optimizations.

## When to use

- Before changing anything whose motivation is speed or memory.
- Adding batching, engine reuse, caching, or concurrency.
- Writing release notes that mention performance.

## Relevant modules

- `src/documind/ocr/engine.py` (lazy init, model load)
- `src/documind/tables/pipeline.py`, `src/documind/web/` (service layer)
- `assets/samples/` (fixed benchmark inputs)

## Rules

- Measure first: record cold init, warm inference, and per-document time
  on fixed inputs, fixed settings (same machine, CPU, thread count).
- Report methodology with the numbers (input, machine class, runs); if
  benchmarking is not possible, say so instead of estimating.
- Correctness outranks speed; do not weaken validation to go faster.
- Reuse of an OCR engine across calls must stay thread-safe (lock or
  single-consumer design).

## Workflow

1. Write a small timing script under `scripts/` printing a table
   (no magic numbers in code).
2. Capture the baseline into the PR description.
3. Apply one change; re-measure; keep it only with a reproduced win.
4. Note any regression in warm-up behavior or memory.

## Verification

```
python scripts/verify.py          # correctness gate still green
python scripts/<timing-script>.py # before/after comparison
```

## Failure and rollback criteria

- Revert any optimization that changes outputs or drops error handling.
- Revert if the measured win is within noise on repeated runs.
- Never merge a PR containing performance percentages without recorded
  measurement output.
