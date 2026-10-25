# Product Expansion Plan — DocuMind AI

Prioritized plan for turning DocuMind AI into a polished, portfolio-worthy
Document Intelligence application. Status is maintained here so work can
resume after context loss.

**Ground rules:** quality over quantity; no invented benchmarks or
accuracy claims; real-document evaluation stays pending user-provided
labeled data; PRs are vertically sliced and stay open for review;
prefer completing PR B (web app) correctly over partially doing B–E.

## Progress checklist

- [x] Phase 0 — repository audit and baseline (main @ 7e7621f post PR #5, 223 tests green)
- [x] Phase 1 / PR A — quality foundations + agent skills (this PR)
- [x] Phase 2 / PR B — M5A: local FastAPI backend + web frontend
- [x] Phase 3 / PR C — M5B: PDF input, batch processing, richer exports
- [ ] Phase 4 / PR D — M5C: extraction robustness + Vietnamese labels/i18n (pending — next stacked PR; design notes: label lexicon separated from parsing, VND symbols, no metric redefinitions)
- [ ] Phase 5 / PR E — performance profiling + release polish (pending — benchmark script + cold/warm inference measurement first)
- [ ] Phase 5 / PR E — performance profiling + release polish

## PR A — Quality foundations (done)

Acceptance criteria:
- [x] Ruff lint clean across `src/`, `tests/`, `scripts/`; enforced in CI.
- [x] `python scripts/verify.py` = ruff + pytest in one command.
- [x] `AGENTS.md` documents architecture, commands, privacy, metric rules, DoD.
- [x] Four focused agent skills under `.agents/skills/`.
- [x] README/pyproject no longer carry stale totals or hardcoded test counts.
- [x] Full test suite green; CI green.

## PR B — M5A: local web application (done, stacked on PR A)

Goal: local-first FastAPI backend + vanilla JS frontend reusing the
existing pipelines. Endpoint contracts documented; uploads untrusted
(size/extension/content validation, temp cleanup, bounded inference
concurrency, no public binding). Human-in-the-loop corrections keep
machine output and user corrections separate. Acceptance:
- [x] All endpoints tested with mocked inference including error paths
      (24 web tests: security, exports read-back, HITL payload).
- [x] Synthetic receipt processed end-to-end through the API with real
      inference (30 OCR regions, invoice total 13.53, status ok).
- [x] Bounding boxes scale with the preview image; provenance highlight
      on hover/focus (implemented in app.js; UI walkthrough pending user).
- [x] Invoice fields and table cells editable; corrections exported
      alongside original machine output (`machine_output` +
      `user_corrections`).
- [x] CLI tools unchanged (223 pre-existing tests still green).
- [x] API contract documented: docs/web-api.md.

## PR C — M5B: PDF, batch, exports (pending)

pypdfium2-based PDF input (page images, per-page provenance, page
limits), bounded batch processing with per-file errors and partial
success, ZIP/CSV/XLSX exports with formula-injection and filename
sanitization. Acceptance: deterministic multi-page fixtures, batches
isolate errors, exports read back, single-image behavior unchanged.

## PR D — M5C: extraction robustness / i18n (pending)

Vietnamese label lexicon (HÓA ĐƠN, TỔNG CỘNG, THUẾ, ...) separated from
parsing, VND currency labels/symbols, documented Vietnamese number
formats, table-recognition robustness (jitter, thickness, multiline) —
each with regression tests and no metric redefinitions.

## PR E — Performance + release polish (pending)

Measured baselines (cold init, warm inference, per-image time) before
any optimization; engine reuse in batch; documented methodology; then
screenshots/demo walkthrough and release checklist. No invented numbers.

## Stage 0 (P0 repair) — done on PR #8 branch

- [x] 0.1 CRITICAL: app.js had a top-level `return` (orphaned batch-zip
      block) — the whole frontend script failed to load. Fixed; batch
      export now also excludes failed documents explicitly
      (`batch-errors.json`). Regression gate added:
      `scripts/check_browser_js.py` EXECUTES app.js under Node with DOM
      stubs (catches runtime load errors that `node --check` misses);
      wired into verify.py + pytest (`tests/test_frontend_gate.py`).
- [ ] 0.2 frontend state consistency across files/pages — PENDING (next unit)
- [ ] 0.3 pdf.py preflight dimension check before bitmap allocation — PENDING
- [ ] 0.4 export hardening sweep — partially covered by earlier tests; full audit PENDING

## Resume instructions (context exhausted 2026-10-25)

1. `git checkout feat/m5b-pdf-batch-exports` (head after Stage 0.1 fix).
2. Do Stage 0.2–0.4 (see PR #8 review findings), then Stages D–H per the
   original mission; each is a stacked branch off the previous head.
3. Keep the frontend gate green: `python scripts/check_browser_js.py`.

## Known issues at audit time

- README carried stale sample totals and hardcoded test counts (fixed in PR A).
- No linting gate previously; several style violations had accumulated (fixed in PR A).
- Real-document evaluation data: none available; onboarding tooling ready (M4B Phase 1).
