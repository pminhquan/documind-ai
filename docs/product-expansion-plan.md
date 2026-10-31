# Product Expansion Plan — DocuMind AI

Prioritized milestone plan for DocuMind AI. This file is the single
current roadmap; it is updated when milestones are delivered so work can
resume after context loss. Historical planning is kept in
[Historical context](#historical-context) and must not be read as current
work.

**Post-D18 release checkpoint (historical):** `main` @
`130f32207e316330cba15d31c23558c6a2987607` (merge commit of PR #13,
2026-10-27). Main CI: [run 40439790177](https://github.com/pminhquan/documind-ai/actions/runs/40439790177)
— success, ruff clean, frontend gate green, 392 tests passing at that
dated checkpoint. Future HEADs may have a different test count; check
CI.

**PR #15 base checkpoint (historical):** `origin/main` @
`31a8f1bde0328402cb976b7e0f257871ebc2848b` (PR #14 merge, 2026-10-27;
does not contain D-16). Check live `origin/main`/CI for the current
HEAD.

**D-16 merge checkpoint:** `origin/main` @
`231cd909924f75b4d46816ca028bbdca5b6107ef` (PR #15 merge, 2026-10-29;
519 tests; CI run
[40843248171](https://github.com/pminhquan/documind-ai/actions/runs/40843248171)).
D-16's short-receipt line-item extraction is integrated on `main`.

**P3 integration release (2026-10-31):** D-22 is merged via PR #16
(`4d01e78`) and the P3 audit follow-ups via PRs #17–#23 (merge commits
`3f4bab3`, `0df8a68`, `418ac5c`, `e9bcbb0`, `1f10ab9`, `b727bbd`,
`c1528ab`; combined baseline 715 tests) — do not reimplement them.
See `HANDOFF.md` for the full merge/CI record.

**Ground rules:** quality over quantity; no invented benchmarks or
accuracy claims; real-document evaluation stays pending until
privacy-cleared, manually annotated data exists; PRs are focused and
stay open for review; documentation is updated in the same change as
behavior; the project remains local-first with no database or public
deployment in the current scope.

## Current milestone status

| Milestone | Status | Evidence / note |
|---|---|---|
| M0/M1 — OCR baseline | ✅ Complete | PaddleOCR 3.x, PP-OCRv6 CPU, mocked tests |
| M2 — invoice extraction | ✅ Complete | Deterministic rules, Decimal money, validation semantics |
| M3A — ruled tables | ✅ Complete | OpenCV geometry + assignment; ruled grids only |
| M4A — evaluation framework | ✅ Complete | CER/WER, invoice field accuracy, strict table metrics |
| M4B Phase 1 — dataset onboarding | ✅ Complete | Anonymization gate, manual annotation, local predictions |
| M5A — local web app | ✅ Complete | FastAPI + vanilla JS, uploads, workflows, corrections, exports |
| M5B — PDF, batch, page exports | ✅ Complete | PDF page-indexed processing, batch ZIP, D-18 |
| M5C — Vietnamese extraction rules | ✅ Complete (extraction layer) | Labels + VND money rules; **OCR recognition not validated** |
| M5D — performance baseline | ✅ Complete (synthetic/local) | `reports/benchmark-local.md`; runtime numbers, not accuracy |
| Post-audit regression fixes | ✅ Integrated | P1/P2 audit fixes, D-17, D-19, XLSX title safety |
| D-16 — short-receipt line items | ✅ Merged | PR #15 merge commit `231cd9`; headerless extraction integrated and tested |
| D-22 — malformed eval inputs | ✅ Merged (PR #16) | Structural validation for prediction/ground-truth data; merge commit `4d01e78` on `main` |
| P3 audit batch — D-20, D-23/D-24, D-28–D-34 | ✅ Merged (PRs #17–#23) | Signed totals, two-digit years + locale-free months, dataset lifecycle guards, word-level qty × price, header provenance, line tolerance, temp cleanup, OCR JSON guard; merge commits `3f4bab3`…`c1528ab` |
| M4B Phase 2 — real-document evaluation | 🔲 Pending | Blocked on privacy-cleared, manually annotated data |
| M3B — borderless tables | 🔲 Deferred | Model-based structure recognition; later milestone |

## Delivered work

### M5A — local web application

FastAPI service + no-build vanilla JS frontend, bound to `127.0.0.1`.
Images can be processed through OCR, invoice, table, or Auto workflows;
results are editable, machine output is immutable, and corrections are
exported alongside it. Upload validation, temp cleanup, serialized
inference, and export safety are covered by tests.

### M5B — PDF, batch, richer exports (including D-18)

- Multi-page PDFs render via `pypdfium2` with hard limits (10 pages,
  30 MP/page, 60 MP cumulative, 15k points/side) and page-indexed
  results; per-page failures are explicit.
- D-18 added page-local exports, opaque document identity (so duplicate
  filenames never mix corrections), page switching/restoration, and
  per-page/per-family Reset.
- Batch runs process up to 10 files sequentially with partial success,
  explicit failures, and a batch ZIP that preserves complete PDF page
  data, image Auto artifacts, and page-local corrections.
- ZIP names are sanitized, case-insensitively unique, extension-
  preserving, and capped; `batch-errors.json` is the first entry when
  failures exist. The server also enforces export payload bounds.

### M5C — Vietnamese extraction rules

Vietnamese invoice labels (diacritic-insensitive) and VND money formats
are implemented and tested at the extraction layer. This is **not**
evidence of Vietnamese OCR accuracy; the default model remains English
and recognition quality is unmeasured.

### M5D — performance baseline

`scripts/benchmark.py` records reproducible local CPU measurements
(cold engine init, warm OCR, extraction, table geometry, unified request)
in `reports/benchmark-local.md`. These are runtime measurements on
synthetic input, not recognition-accuracy results.

## Integrated quality fixes

- **2026-10-26 baseline audit:** fixed 4 P1 defects (merged-row money
  loss, summary-zone keyword gaps, invoice CSV/XLSX routing, table
  correction paths) plus P2/P3 issues with regression tests; the
  historical audit and its open backlog remain in
  `reports/audits/2026-10-26-baseline-audit.md`.
- **D-17:** malformed table export payloads now return 422 with stable
  details instead of 500; worksheet titles are sanitized, capped, and
  deduplicated.
- **D-19:** API responses use stable `upload` / `upload#pageN` labels and
  never disclose server temp paths.
- **D-18:** page-level exports, correction identity/lifecycle, batch
  preservation, case-insensitive ZIP naming, and the reserved failure
  report.
- **Post-audit verification:** ruff + Node frontend gate + pytest are
  required in `python scripts/verify.py` and CI.

## Known limitations

- Ruled tables only; borderless/partial/rotated tables unsupported
  (M3B deferred).
- No cross-page invoice aggregation; PDF extraction is per page.
- Vietnamese OCR recognition unvalidated; extraction rules only.
- No database, job queue, resume, or multi-user deployment; batch runs
  are sequential in the browser.
- Batch results panel shows the last processed document; no full batch
  navigator.
- A very long source stem can lose its extension in a single-file
  export download header (batch ZIP is safe).
- CSV exports are UTF-8 without BOM (D-21).
- All automated tests use mocked/synthetic/geometry-only inputs; the
  benchmark and historical smoke tests are not real-world accuracy
  evidence. M4B Phase 2 is the only path to genuine metrics.
- Open defects include other P3 audit items; D-22's input validation is
  implemented in its Draft PR (check the live PR and current `main` HEAD
  for integration status). D-16 is integrated on `main`. Revalidate the
  audit against current code before starting remaining items.

## Next tasks

D-16 is integrated on `main` (PR #15, merge commit `231cd9`). D-22's
input validation is implemented in its Draft PR; verify the live PR and
current `main` HEAD before assuming integration. After D-22, the
remaining tasks below are ordered by prerequisite value; no new
milestone should begin without its data/decision dependency.

1. **Relevant P3 audit items.** Revalidate and prioritize
   export/data-integrity defects (e.g. D-20 locale-sensitive parsing,
   D-21 CSV BOM, D-23/D-24 dataset lifecycle) ahead of speculative
   features.
2. **M4B Phase 2 — real-document evaluation.** Collect 10–20
   privacy-cleared documents (Vietnamese receipts, invoice-style pages,
   ruled-table pages), annotate by hand, onboard with
   `documind-dataset`, predict, and evaluate with `provenance: real`.
   Publish the first honest accuracy report. Data collection may proceed
   in parallel with task 1.
3. **Vietnamese OCR benchmarking.** Compare `lang="vi"` vs `lang="en"` on
   the real evaluation set; record a model-selection decision before
   tuning.
4. **M3B — borderless table recognition.** Deferred until ruled-table
   evidence and real-document evaluation are established.

## Historical context

The following is history, not current work. It explains how the project
reached the current checkpoint and which decisions remain in force.

- **Phase 0 — repository audit and baseline:** pre-M5A snapshot (main
  @ `7e7621f`, post PR #5) with 223 tests green at the time; identified
  quality gaps, stale docs, and missing gates.
- **Phase 1 / PR A — quality foundations + agent skills:** ruff gate,
  `scripts/verify.py`, `AGENTS.md`, agent skills. Decision: no hardcoded
  test counts in prose; CI is the source of truth.
- **Phase 2 / PR B (M5A):** local web app with endpoint contracts,
  security validation, and human-in-the-loop corrections.
- **Phase 3 / PR C (M5B):** PDF input, batch processing, ZIP/CSV/XLSX
  exports, formula-injection protection and filename sanitization. The
  original plan listed this as pending; it was delivered, then hardened.
- **Phase 4 / PR D (M5C):** Vietnamese label/VND extraction rules,
  separated from parsing; no metric redefinitions.
- **Phase 5 / PR E (M5D):** measured local performance baseline before
  any optimization; no invented numbers.
- **Stage 0 repairs:** frontend top-level load failure fixed, browser
  regression gate added, PDF preflight and export hardening completed.
  The old Stage 0.2–0.4 "pending" checklist is superseded by delivered
  work and tests.
- **D-18 (PR #13):** closed the PDF page-export gap and the remaining
  identity/ZIP naming defects. Three commits merged by merge commit
  `130f322`; main CI verified.
- **Decisions retained:** local-first, no database/deployment; metrics
  and denominators change only with spec + regression tests; synthetic
  results are never presented as real-world accuracy; borderless tables
  stay deferred behind real-data evidence.

Obsolete instructions from earlier drafts ("resume from
`feat/m5b-pdf-batch-exports`", "next stacked PR", duplicate Phase 5) are
removed. Git history retains the old plans if needed.

## Agent handoff

1. Inspect Git: `git status --short`, `git branch --show-current`,
   `git fetch origin`, `git rev-parse origin/main`.
2. Read `AGENTS.md` and `HANDOFF.md` before editing.
3. Check live Git: D-16 (PR #15), D-22 (PR #16) and the P3 audit batch
   (PRs #17–#23) are integrated on `main`; do not reimplement them.
   Read `HANDOFF.md` for the merge/CI record before assuming status.
4. Base new work on the latest verified `origin/main`, not a stale local
   `main`; prefer a dedicated worktree.
5. Create a focused branch (`feat/<milestone>-<slug>` or `docs/<slug>`).
6. Run `python scripts/verify.py` before committing/pushing.
7. Open a Draft PR with the verified checkpoint and test evidence; do not
   merge without explicit owner authorization; never force-push or
   rewrite history.
8. Update README/HANDOFF/this plan when milestone state changes. Use a
   dated checkpoint for test counts; do not assert a permanent total.
