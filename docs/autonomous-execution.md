# Autonomous Execution Checkpoint (historical)

> **Superseded — historical record.** This file documents an autonomous
> session on 2026-10-25 (session 4). Its PR list, test count, and restart
> instructions are no longer current. All four PRs below were later
> merged; current `main` is `130f322` (PR #13 merge, D-18 complete) with
> 392 tests as of 2026-10-27. For current state, commands, and next work,
> see [HANDOFF.md](../HANDOFF.md) and
> [product-expansion-plan.md](product-expansion-plan.md).

## Final state of that run (2026-10-25, session 4) — QUEUE COMPLETE

- Working branch pushed last: `feat/m5d-performance` (PR #10, CI green,
  head `c757778`)
- PR graph at the time (all OPEN, stacked; merge order #7 → #8 → #9 → #10,
  none auto-merged):
  1. #7  feat/m5a-web-app            (base main-merged #6) head 3c580ed
  2. #8  feat/m5b-pdf-batch-exports  (base #7)  head ade7cce — Stage 0 done
  3. #9  feat/m5c-vietnamese-documents (base #8) head — VI extraction
  4. #10 feat/m5d-performance        (base #9)  head c757778 — benchmark
- Tests at the time: 295 passed local + CI on every final head; ruff
  clean; frontend browser gate green and enforced in CI (setup-node).
- Benchmark baseline (real CPU): cold init 3.66s, warm OCR 17.02s median,
  invoice extraction 9.1ms, geometry 3.6ms, unified 16.87s @ 1 init +
  1 OCR call. Evidence: reports/benchmark-local.md.

## Completed in that run

- [x] Stage 0.2 PDF preflight (MediaBox before bitmap; 15000pt/30MP/60MP budgets)
- [x] Stage 0.3 invoice XLSX XML-illegal char strip (was a 500)
- [x] Stage 0.1 frontend state: corrections per file+page, overlay cleanup,
      reset per active doc, unsaved-count indicator
- [x] Stage 0.4 CI setup-node + browser gate as an explicit step
- [x] M5C Vietnamese extraction lexicon (diacritic-fold, đ-safety, VND)
      + 18 tests, English regression green
- [x] M5D benchmark harness + first honest baseline; conclusion recorded:
      warm OCR dominates; no code-tuning optimization justified without
      a model-selection decision

## Backlog recorded at the time

- Stage E full fault-tolerance sweep; Stage F review workspace UX
  (side-by-side, review statuses); Stage G table robustness (thin/thick
  lines, skew); Stage H release/portfolio docs + screenshots
- Optional: Vietnamese OCR recognition validation with lang='vi' model
  (requires benchmarked model decision — see D5 reality check)
- Real-document evaluation still PENDING user-provided labeled data

Most of this backlog is now tracked in
[product-expansion-plan.md](product-expansion-plan.md) (D-16, D-22, P3,
M4B P2, Vietnamese OCR benchmarking; M3B deferred).

## Restart instructions (obsolete)

The original instructions said to check out `feat/m5d-performance` and
create a stacked branch. Do **not** use them: that stack was merged into
`main`. Current workflow starts from `origin/main` (`130f322`):

1. `git fetch origin && git checkout -b <branch> origin/main`
2. Verify gates: `python scripts/verify.py` (ruff + browser gate + pytest)
3. Pick the next item from HANDOFF.md "Next Work", follow AGENTS.md and
   `.agents/skills/*`.

## Machine action

Historical note: the user instructed the machine to shut down when the
queue completed (sleep as fallback); this was executed at the end of that
run. Not a standing instruction for future sessions.
