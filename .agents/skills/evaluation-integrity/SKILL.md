---
name: evaluation-integrity
description: Work on DocuMind evaluation metrics, manifests, or reports (src/documind/evaluation) — use when touching metric definitions, denominators, aggregation, or evaluation docs.
---

# Evaluation integrity

## Purpose

Keep the evaluation framework honest: stable metric definitions,
reproducible numbers, no accuracy inflation.

## When to use

- Changing anything in `src/documind/evaluation/` (metrics, aggregation,
  reports, manifest schema).
- Interpreting or publishing evaluation numbers.

## Relevant modules

- `src/documind/evaluation/{text_metrics,ocr_eval,invoice_eval,table_eval}.py`
- `src/documind/evaluation/{manifest,report,cli}.py`
- `docs/evaluation-spec.md` (normative definitions)
- `reports/m4a-synthetic-baseline.md` (regression baseline)

## Rules

- Denominators, null semantics, and matching assumptions are part of the
  contract: changing any of them requires updating `docs/evaluation-spec.md`
  and regression tests in the same change, with hand-computed expected values.
- Never use model confidence as an accuracy metric.
- Never present synthetic numbers as real-world accuracy; provenance
  (`synthetic|real|unknown`) must flow through summaries and reports.
- Baseline numbers may change only because definitions changed — explain
  the diff in the PR.

## Workflow

1. Write the failing regression test with hand-computed expected values.
2. Fix the metric; update the spec.
3. Re-run all three synthetic evaluations and compare old vs new numbers.

## Verification

```
python scripts/verify.py
documind-eval --task ocr     --manifest data/eval/synthetic/ocr/manifest.json
documind-eval --task invoice --manifest data/eval/synthetic/invoice/manifest.json
documind-eval --task table   --manifest data/eval/synthetic/table/manifest.json
```

## Failure and rollback criteria

- If existing synthetic baselines change without a definition change,
  treat it as a bug and revert.
- If a metric becomes ambiguous (two plausible denominators), stop and
  split it into two explicitly named metrics.
