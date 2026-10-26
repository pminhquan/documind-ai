# DocuMind AI — Baseline Technical Audit

**Date:** 2026-10-26
**Scope:** Full-repository verification, code audit, controlled fixes, next-milestone readiness.
**Branch audited:** `feat/m5d-performance` (head `d42ca6e`) — the tip of the open PR stack #7→#10. **Post-audit review (same day):** fixes were independently re-verified on `fix/post-m5d-audit-regressions` (matrix-based D-01 checks, end-to-end D-03/D-04 payload validation, full gate); two additional defects inside the original D-01 fix were caught and repaired — see the D-01 row and tests `test_space_grouped_integer_total` / `test_stray_single_digit_cannot_win_rightmost`.
**Method:** 3 independent audit passes (OCR+extraction; tables+evaluation; web+dataset+CLI), every candidate finding re-verified against exact source lines, and dynamic reproduction with the project's own Python 3.12 venv before a finding was classified "confirmed".

---

## A. Executive Summary

**Overall project health: GOOD — the handoff's claims are substantially accurate, with one structural caveat about merge state.**

- `python scripts/verify.py` passes on the audited head: **ruff clean, frontend browser gate green, 295→315 tests passing** (20 regression tests: 18 from the audit + 2 added by the independent review).
- The deterministic core (money parsing, validation semantics, table geometry/assignment, evaluation metrics, dataset privacy gating) survived an adversarial audit without a single P0. That is a genuinely strong baseline.
- The handoff's milestone table is accurate **for the branch it describes**, but it under-states one fact: **`main` only contains PRs #1–#6.** M5A/M5B/M5C/M5D live on four OPEN stacked PRs (#7→#8→#9→#10, all CI-green, none merged). "M5A complete" is true on the stack; it is not yet true of `main`.
- This audit found and fixed **4 confirmed P1 defects** (2 extraction correctness, 2 frontend export) plus 3 P2 and 8 small P3 defects, all with regression tests. All fixes are uncommitted working-tree changes on `feat/m5d-performance`, left for review per the repo's no-auto-commit rule.

**Highest-priority risks (pre-fix):** silent financial-data loss in extraction (integer VND totals dropped on merged OCR rows), a valid receipt being branded `invalid` (summary-zone keyword gap), and the web UI exporting a near-empty invoice with HTTP 200 (silent wrong-data export).

---

## B. Actual Milestone Status

| Milestone | Handoff status | Verified status | Evidence | Remaining work |
|---|---|---|---|---|
| M0/M1 OCR baseline | ✅ Done | **Implemented and tested** (mocked; real inference smoke-tested previously, models present locally ~133 MB) | `src/documind/ocr/*`, lazy import, MKLDNN guard with documented Windows rationale | Real VN recognition accuracy (M5C scope) |
| M2 Invoice extraction | ✅ Done | **Implemented and tested**, with 2 P1 + 3 P2 defects found and fixed in this audit | `extraction/*`, 82→95 tests | Real-data validation (M4B P2); merged-row integer totals now fixed |
| M3A Ruled tables | ✅ Done | **Implemented and tested** — no P0/P1/P2 found; geometry was exercised against degenerate images (10×10, constant color) without failure | `tables/*`, audit pass 2 | Borderless (M3B, planned) |
| M4A Evaluation | ✅ Done | **Implemented and tested** — metrics hand-verified (Levenshtein backtrace invariant over 200 random pairs; strict table denominators recomputed); 3 one-line P3 contract leaks fixed | `evaluation/*` | None blocking |
| M4B Phase 1 dataset onboarding | ✅ Done | **Implemented and tested**; privacy posture confirmed (traversal-proof IDs, `--confirm-anonymized` gate, `data/eval/real/` git-ignored, GT provably never derived from predictions) | `dataset.py`, `dataset_cli.py` | Lifecycle nits (see F-23/F-24, deferred P3) |
| M5A Web app | ✅ Done (branch) | **Implemented and tested on PR #7 stack; NOT yet on `main`** — 2 P1 frontend export defects found and fixed | `web/*`, audit pass 3 | Merge of PR #7 |
| M5B PDF/batch | "partially implemented" per task brief | **Actually implemented and well-hardened on PR #8**: PDF preflight (MediaBox before bitmap, 15k pt / 30 MP/page / 60 MP cumulative, ≤10 pages), batch ZIP, per-page corrections; 2 export-path defects fixed, recursion hole closed | `web/pdf.py`, `web/app.py`, `test_web_pdf_batch.py` | Cross-page invoice logic (explicitly out of scope by design) |
| M5C Vietnamese | Pending | **Partially implemented on PR #9**: extraction-level VI labels/đ/VND rules exist and are tested; **VN OCR recognition still NOT validated** (`lang="en"`) | `lexicon_vi.py`, `test_extraction_vi.py` | `lang="vi"` model validation (needs benchmark decision) |
| M5D Performance | Not in brief | **Implemented on PR #10**: reproducible local benchmark (cold init 3.66 s, warm OCR ~17 s median, extraction 9.1 ms) — honest CPU baseline, no premature tuning | `reports/benchmark-local.md` | Model-selection decision before any optimization |
| M4B Phase 2 | Pending | **Pending — not startable without labeled real documents** (no `data/eval/real/` exists yet) | — | User-provided, privacy-cleared, manually annotated docs |
| M3B Borderless | Planned | Missing (by design) | — | Deferred; see §G |

**Feature-inventory states used:** implemented+tested / implemented-insufficiently-tested / partial / documented-only / missing — see table above; nothing was credited on file presence alone.

---

## C. Verification Results

Executed on Windows 10 (10.0.26200), Git Bash, project venv Python **3.12.10** (system Python 3.14 correctly NOT used):

| Command | Result |
|---|---|
| `python scripts/verify.py` (pre-fix baseline) | ✅ ruff clean, frontend gate green, **295 passed** in 5.37 s |
| `python scripts/verify.py` (post-fix + review) | ✅ ruff clean, frontend gate green, **315 passed** in ~5.8 s |
| `ruff check src tests scripts` | ✅ clean (11 auto-fixable style findings in the new test code were fixed) |
| `pytest -q` targeted suites during fixes | 82→95 extraction, 52 web, 117 extraction+eval, 26 CLI+batch — all green at each step |
| CI (`gh run list`) | PR #10 head `c757778`/stack heads: **success** (ruff + node browser gate + pytest, Python 3.12, no PaddlePaddle, no model downloads, no GPU) |
| Real-inference smoke | Not re-run in this audit session; PP-OCRv6 weights present at `~/.paddlex` (133 MB) from prior sessions — previous sessions recorded real CPU inference (benchmark report). All 313 CI/local tests remain mocked/geometry-only. |
| Frontend behavioral check (new) | Node 24 `vm` harness executes `app.js` + asserts export payload shapes — green |

**Test-class breakdown (unchanged by this audit):** all automated tests are mocked/synthetic/geometry-only. No test claims real OCR accuracy; every evaluation number in `reports/` remains synthetic-provenance.

**Environment limitations:** MKLDNN disabled on Windows (documented PaddlePaddle 3.x CPU crash); real-data evaluation blocked solely on user-annotated documents.

---

## D. Audit Findings

Severity: P0 critical · P1 major correctness · P2 significant · P3 minor. "Fixed" = in this audit's working-tree changes. Line numbers refer to the pre-fix revision of `feat/m5d-performance` (d42ca6e).

### P1 — fixed

| ID | File | Problem | Evidence | Fix |
|---|---|---|---|---|
| **D-01** | `extraction/extractor.py` `_rightmost_amount` (~L137–152), `parsing.py` | Merged-text fallback searched only `MONEY_TOKEN_RE` (requires 2-digit fraction) → integer/thousands-grouped amounts in merged single-region rows were **silently dropped**: `TONG CONG: 20.000` → `total=None`; merged item row `CA PHE 2 x 10.000 20.000` lost its line total. VND totals have no decimal fraction, so the natural single-region rendering of a Vietnamese total returned nothing. | Reproduced by execution on branch (pre-fix): totals `None`; the repo's own `outputs/sample_receipt.json` shows label+value in ONE region (`Receipt #: 00001234`). | New `MERGED_MONEY_RE` in `parsing.py` accepts all three token shapes with the same lookaround discipline; used by `_rightmost_amount` and the item-row tail scan. **Refined during review:** the grouped branch accepts space separators (`1 234 567`, previously degraded to the rightmost group `567`) and bare integers require ≥2 digits (a stray single digit in `97.20 0` previously won the rightmost rule and returned `0`). Trade-off documented: a bare multi-digit run (a year) can match when the fallback fires — validation surfaces a wrong value instead of silence. Regression: `TestMergedAmountRows` (6 tests), `TestSummaryZoneOpeners.test_merged_integer_total_vnd`. |
| **D-02** | `extraction/extractor.py` `SUMMARY_START_RE` (~L41–44, 65–70) | Zone-opener regex was inconsistent with `SUMMARY_LABELS_VI`: bare `thue`, `khach dua`, `tien mat` missing → a cash/tax row printed before the subtotal stayed in the ITEM region, became a **bogus line item**, and tripped a **false `invalid`** verdict on a fully consistent receipt (`items=[SOAP, TIEN MAT:]`, `errors=['subtotal != sum(line_items)']`). | Reproduced by execution (pre-fix). | Added `thue`, `khach dua`, `tien mat` to the VI opener alternation (also removed a no-op `.replace(r"\b", r"\b")` on the line). Regression: `TestSummaryZoneOpeners` (3 tests) — cash-before-subtotal now yields `status="ok"`. |
| **D-03** | `web/static/app.js` `buildExportPayload` (~L480–525) | `invoice-csv` / `invoice-xlsx` were not handled and fell into the **tables** fallthrough → clicking Export CSV/XLSX in the invoice panel POSTed `machine_output = machine.tables`; the server found no `invoice` key and returned **HTTP 200 with a near-empty invoice file** (only user-typed corrections). Affects images and PDF pages. | Traced payload shape; server reads `data.machine_output.invoice` (`app.py` `_build_export`); server tests only ever posted the correct shape the frontend never produces. | `kind.startsWith("invoice")` routes CSV/XLSX/JSON through the invoice payload; per-kind filenames. Regression: Node behavioral test `test_export_payload_behavior` (asserts payload shape for all 5 kinds). |
| **D-04** | `web/static/app.js` `pickCorrections("tables")` (~L435, 522, 527–533) | Table corrections recorded as `tables[T].cells[R][C]` were stripped to `[T].cells[R][C]` (no dot after `tables`); the server regex `^tables\[(\d+)\]...` never matched → **422 on every table CSV/XLSX export once a single cell was edited**; `table-json` exported corrupted keys that a consumer replaying them would see rejected. | Verified under Node; server contract in `app.py` `CORRECTION_PATH_RE` + `_apply_table_corrections`. | `pickCorrections(prefix, keepPrefix)` — table corrections sent verbatim; table export filenames per kind (`tables.csv` / `tables.xlsx` / `tables-result.json` instead of extension-less `tables-result`). Regression: Node behavioral test. |

### P2 — fixed

| ID | File | Problem | Fix |
|---|---|---|---|
| **D-05** | `extraction/extractor.py` `INVOICE_NUMBER_RE` (~L87–90, 196–207) | All label groups optional → captured the next word on header lines: `Invoice Date: 2026-10-25` → invoice_number `"Date"`; `RECEIPT FROM WALMART` → `"FROM"`; scan then `return`ed, never reaching the real number. Same class existed in the VI pattern (`so hoa don ngay …` → `"ngay"`). | Capture now requires a digit (`(?=[A-Za-z0-9/-]*\d)` lookahead bounded to the capture charset) in both EN and VI patterns. Trade-off: digitless invoice numbers are no longer matched (they were predominantly junk captures). Regression: `TestHeaderFieldRobustness` (3 tests incl. positive `Invoice No: A-123`). |
| **D-06** | `extraction/extractor.py` `extract_supplier` (~L176–187) | Label-only line `"TEN CUA HANG:"` backtracked the regex into capturing the bare `":"`; truthy after strip → supplier `":"` and early return skipped the real name on the next line. | Value stripped of separators and required to contain a word character; otherwise fall through (bare-label `continue`). Regression: `test_label_only_supplier_line_falls_through`. |
| **D-07** | `extraction/extractor.py` `SYMBOL_TO_CODE` (~L91, 234–239) | Currency fallback treated a `đ` **inside any word** (`đơn giá`, `đã`) as the đồng symbol — contradicting `lexicon_vi.py`'s own standalone-token invariant — so any Vietnamese-document line could brand the invoice VND. | Removed `đ`/`₫` from the substring table; standalone signs remain handled by `DONG_SIGN_RE` in the VND pass. Regression: `test_dong_inside_a_word_is_not_currency` + positive standalone test. |

### P3 — fixed (small, verified)

| ID | File | Problem | Fix |
|---|---|---|---|
| D-08 | `evaluation/table_eval.py` (~L83) | JSON `null` GT cell classified by prediction presence (`str(None).strip()` truthy) → skewed non-empty/empty denominators depending on the branch. | Both branches use `_normalize`. Regression added. |
| D-09 | `evaluation/table_eval.py` (~L38) | `bool` passed `isinstance(x, int)` → `true`/`false` coordinates silently addressed cells, contradicting the documented "non-integer coordinates are extra" rule. | Bool explicitly rejected → counted unexpected with issue. Regression added. |
| D-10 | `evaluation/cli.py` (~L39) | `--case-sensitive` help claimed OCR/**table**; only OCR honors it. | Help corrected to "OCR task only". |
| D-11 | `web/app.py` (~L394) | `batch-zip` was a legal **inner** entry kind → client-supplied entries could recurse unbounded (RecursionError → 500). | Inner kinds exclude `batch-zip` → 422. Regression added. |
| D-12 | `web/app.py` (~L236) | `MAX_BATCH_EXPORTS` defined twice (equal today, divergence trap). | Duplicate removed. |
| D-13 | `cli.py` (~L74–81) | `documind-ocr` didn't catch `OSError` (raw traceback on e.g. unwritable output; sibling CLIs map it to exit 1). | `except OSError` added; regression: write-to-directory test. |
| D-14 | `scripts/check_browser_js.py` | DOM stub `classList` lacked `contains` (a stub gap — browsers always have it) blocking behavioral testing. | `contains() { return false; }` added to the prelude. |
| D-15 | `tests/test_frontend_gate.py` (~L31–42) | The load-gate test mutated the **real** `app.js` (restore-in-finally) — a killed runner could ship a corrupted frontend. | Test now mutates a `tmp_path` copy. |

### P3 — documented, deferred (with reasons)

| ID | Location | Issue | Why deferred |
|---|---|---|---|
| D-16 | `extraction/extractor.py` (~L261) | No-header heuristic `start = 3` drops ALL line items on ≤3-line kiosk receipts (documented in spec; consequence is item loss, not corruption). | Needs a letterhead-detection redesign, not a one-liner; real receipts from the pipeline carry ≥4 lines. |
| D-17 | `web/app.py` `_table_result_from_payload` (~L172–219) | Malformed `/api/export` table payloads can 500 instead of 422 (unknown cell keys `TypeError`, non-dict table, `rows:"abc"`, out-of-bounds cell indices, `table_id` with openpyxl-illegal sheet chars). No amplification beyond a self-500. | Fix = a small validation layer + sheet-title sanitization; belongs in the next PR with its own test set (see §H). |
| D-18 | `web/static/app.js` | PDF per-page invoice/table results are not exportable (exports read only top-level `machine.invoice`/`machine.tables`); batch ZIP of `auto` results carries only OCR JSON. | Design decision needed (page-local export vs. disabled buttons + messaging); not a silent failure (422 surfaced). |
| D-19 | `web/service.py` (~L63, 141–143) | API responses disclose absolute temp paths (`source`/`source_image`). Local-only deployment mitigates. | One-line fix candidate; batched with D-17. |
| D-20 | `extraction/parsing.py` (~L35) | `%b/%B` month names are locale-sensitive (`LC_TIME`); a host calling `setlocale` could change which months parse. | Replace with explicit month table in M5C. |
| D-21 | `tables/exporters.py` (~L78) | CSV is UTF-8 without BOM → Excel-on-Windows mojibakes Vietnamese; data intact, LibreOffice/explicit import fine. | One-word fix (`utf-8-sig`) or documented limitation; needs a product decision on default. |
| D-22 | `evaluation/*` | Malformed prediction/truth structures (non-dict line items/cells, missing `rows`) raise `AttributeError`/`KeyError` past the CLI's clean-error tuple. | Add structural validation raising `ValueError` in each `evaluate_document` (small; next PR). |
| D-23 | `dataset.py` (~L117–135) | `add` works on an uninitialized dataset (creates layout without README/confirmation flow). | Policy gap; trivial guard next PR. |
| D-24 | `dataset.py` (~L258–296) | `validate`'s "ready to evaluate" ignores manifest/annotation-set drift (new annotations after last `predict` not flagged; `predict --task invoice` doesn't refresh `manifest-ocr.json`). | Small correctness-of-tooling fix next PR. |
| D-25 | `evaluation/manifest.py` (~L103–105) | Manifest relative paths allow `../` traversal — **not a vulnerability** (absolute paths already supported by design; the manifest is the trust boundary). | Document in spec: "manifest paths may point anywhere the user can read." |
| D-26 | `web/app.py` (~L479–495) | PDF branch of `/api/process` accepts any extension with `%PDF-` magic (deliberate inverse of the 415 test); bounded by pdf.py budgets. | Document magic-sniff precedence in the module docstring. |
| D-27 | `web/static/app.js` (~L57–61) | Batch correction keys collide for same-named files from different folders (`name#page`). | Key on `name#size#page` (frontend-only). |
| D-28 | `extraction/extractor.py` (~L94), `parsing.py` (~L60–69, 83–84) | Dead code: unused `MAX_OCR_JSON_BYTES` (the 50 MB guard was never wired in), unused `to_decimal`, dead assignment, no-op replace (removed with D-02). | Wire in the byte guard or delete, next PR. |
| D-29 | `extraction/parsing.py` `MONEY_TOKEN_RE` (~L45), `extractor.py` `_is_money_token` | Minus signs are dropped from money values: `MONEY_TOKEN_RE` has no optional `-`, and only bare integers accept a sign at token level, so a credit/refund total `TOTAL -5.00` becomes `5.00`. For `total = subtotal + tax − discount` the drop is accidentally benign, but a negative total misparses. | Make the sign explicit in the token shapes and define a documented policy, next PR. |
| D-30 | `extraction/parsing.py` `DATE_FORMATS` (~L27–38) | Two-digit years parse only in the slash format (`25/10/26`); `25.10.26` and `25-10-26` return `None`. | Add `%d.%m.%y` / `%d-%m-%y` after their 4-digit variants. |
| D-31 | `extraction/extractor.py` `_parse_item_line` (~L366) | Word-level tokenization (one OCR region per word) classifies a bare-integer quantity as a money token, so qty×price is lost (`SOAP 2 x 2.50 5.00` as 5 regions). The pipeline's real PaddleOCR output is line/cell-level where this works. | Exclude bare integers followed by `x`/`*` from `amount_tokens`, or match `QTY_PRICE_RE` against the full line first. |
| D-32 | `extraction/extractor.py` header stages (~L186–238) | Header-field provenance records `line.tokens[0]` (the label region) when the value lives in a different region; line-item/summary provenance is correct. Observed inline shape (`Receipt #: 00001234`) is unaffected. | Locate the token containing the captured value before falling back to `tokens[0]`. |
| D-33 | `ocr/preprocessing.py` (~L34–43) | Temp PNG can leak if conversion raises a non-`OSError` (e.g. `Image.DecompressionBombError`); normal paths clean up correctly. | Broaden the cleanup to `Exception` around the conversion block. |
| D-34 | `tables/assign.py` (~L89) | Reading-order line tolerance anchors on the FIRST token's height, so a tiny leading token (e.g. a comma) can split one visual line. | Use the max/median token height of the line instead. |

**Explicitly checked and cleared (non-findings):** PaddleOCR 3.x API usage and lazy imports; MKLDNN guard; money separator rules end-to-end (`1,234,567.89`, `1.234,56`, `1.234.567`, trailing separators, malformed runs); validator's operand-guarded semantics and status precedence; Decimal scale-insensitive eval comparisons incl. NaN/Infinity/sNaN; null-semantics of invoice eval; strict table metric denominators; manifest validation (task/provenance/duplicates); CSV formula-injection policy (23 adversarial inputs; `−`/fullwidth `＝` correctly left alone); XLSX string-typing + XML char stripping; Content-Disposition and ZIP-entry sanitization (no header injection/traversal); upload validation order (415→413→400→Pillow decode→pixel budget); PDF preflight before bitmap allocation with `document.close()` guaranteed; single `_inference_lock` funnel across all web inference paths; temp cleanup on success+failure; zero dynamic `innerHTML` in the frontend (OCR text reaches the DOM only via `textContent`/`value`).

---

## E. Changes Applied

All changes are **uncommitted working-tree changes on `feat/m5d-performance`** (per repo rule: no commit/push without explicit request). `git status --short` at the end of the audit:

```
 M docs/extraction-spec.md          (spec now matches implemented money/summary/number rules)
 M scripts/check_browser_js.py      (D-14)
 M src/documind/cli.py              (D-13)
 M src/documind/evaluation/cli.py   (D-10)
 M src/documind/evaluation/table_eval.py (D-08, D-09)
 M src/documind/extraction/extractor.py  (D-01, D-02, D-05, D-06, D-07)
 M src/documind/extraction/parsing.py    (D-01: MERGED_MONEY_RE)
 M src/documind/web/app.py          (D-11, D-12)
 M src/documind/web/static/app.js   (D-03, D-04)
 M tests/test_cli.py                (+1 regression)
 M tests/test_evaluation_tasks.py   (+2 regressions)
 M tests/test_extraction.py         (+9 regressions incl. ocr_doc helper)
 M tests/test_extraction_vi.py      (+4 regressions)
 M tests/test_frontend_gate.py      (+1 Node behavioral export test; D-15)
 M tests/test_web_pdf_batch.py      (+1 regression)
?? HANDOFF.md                       (pre-existing untracked user file; test counts updated 295→313)
```

Totals after the review phase: 16 modified files plus the new `reports/audits/` directory and `HANDOFF.md` (sanitized §13), ≈+500/−50 lines, of which the majority are tests. **Every fix carries at least one regression test; no test was weakened, no threshold changed, no valid error suppressed.**

Verification after changes: `python scripts/verify.py` → **ruff clean, frontend gate green, 313 passed**.

---

## F. Remaining Technical Debt (prioritized)

1. **D-17 export 500→422 contract** (P2): malformed client payloads degrade the documented 422 contract into 500s. Small validation layer.
2. **D-18 PDF per-page exports** (P2 UX): per-page invoice/table results visible but not exportable — the PDF workflow's promise is incomplete.
3. **M4B Phase 2 hard dependency** (project-level): zero labeled real documents exist; all accuracy claims must stay synthetic until that changes.
4. **M5C recognition gap** (P2 project-level): extraction has VI rules, but PP-OCRv6 `lang="en"` recognition of Vietnamese diacritics is unvalidated — the biggest known unknown.
5. **D-16 short-receipt item loss**, **D-22 eval malformed-input crashes**, **D-23/D-24 dataset lifecycle**, **D-19 temp-path disclosure**, **D-20 locale-sensitive dates**, **D-21 CSV BOM**, **D-27 same-name batch keys**, **D-28 dead code**, **D-29 sign drop**, **D-30 2-digit-year gaps**, **D-31 word-level qty×price**, **D-32 header provenance**, **D-33 temp-leak edge**, **D-34 assign line tolerance** (all P3, one-PR batchable).

---

## G. Recommended Next Milestone

**Recommendation: do NOT start a new feature milestone yet. First merge the stack, then run M4B Phase 2 as the next milestone.**

Order and rationale:

1. **Land PR stack #7→#10 onto `main`** (merge in order; no force-push; CI is green on every head). Rationale: main is 4 PRs behind the reviewed work; every later milestone builds on M5A/M5B. The 4 P1 fixes from this audit sit on top of #10 — include them in the final merge (reviewer decision: amend into #10's scope or a small follow-up PR).
2. **M5B completion (small)**: D-17 + D-18 + D-19 close the web app's remaining contract gaps (S/M effort, no new deps).
3. **M4B Phase 2 — Real Document Evaluation** (the highest-value milestone): the entire pipeline (onboard → annotate → predict → evaluate → report) is built and tested; the ONLY missing input is user-provided, privacy-cleared, manually annotated documents per `docs/dataset-annotation-guide.md`. Suggested pilot: 10–20 documents (mix: 5–10 Vietnamese receipts, 5 invoice-style, 2–3 ruled-table pages), annotated by the user (ground truth must remain human-made), evaluated with `documind-dataset predict` + `documind-eval` (provenance `real`). This produces the project's first honest accuracy numbers and directly drives M5C priorities.
4. **M5C Vietnamese OCR** (after M4B P2 produces evidence): validate `lang="vi"` vs `lang="en"` recognition on the real set (benchmarked model decision per M5D's conclusion), then targeted extraction fixes.
5. **M3B borderless tables**: keep deferred — model-based structure recognition is a large dependency (new model class), and the ruled-table baseline plus real-data evidence should come first.

**Not started here** (per task constraints): no new milestone implementation, no model downloads, no merges/PRs.

---

## H. Next Sprint Plan

| # | Priority | Task | Files/modules | Dependencies | Definition of Done | Effort |
|---|---|---|---|---|---|---|
| 1 | P0 | Review + commit this audit's fixes; merge PR stack #7→#10 in order | PRs #7–#10 | User review/authorization for merge | `main` contains M5A–M5D; CI green on `main`; audit fixes included | S |
| 2 | P1 | Export contract hardening: 422 (not 500) for malformed table payloads; sanitize `table_id` for sheet titles; placeholder instead of absolute temp paths in responses | `web/app.py`, `web/service.py` | #1 | Adversarial export payloads → 422 with detail; no absolute paths in any response; tests for each rejected shape | S/M |
| 3 | P1 | Dataset lifecycle guards: reject `add` before `init`; `validate` flags manifest/annotation drift; `predict` refreshes sibling manifests | `dataset.py`, `dataset_cli.py` | #1 | Drift case produces explicit validate error; stale manifest never reported "ready" | S |
| 4 | P2 | Eval malformed-input shim: structural validation → clean `ValueError` per document | `evaluation/table_eval.py`, `evaluation/invoice_eval.py` | #1 | Malformed prediction/truth → `Evaluation error:` + exit 2, never a traceback | S |
| 5 | P2 | PDF page-level export UX decision + implementation (page-local payloads or explicit disable+message); batch ZIP keeps per-page invoice/tables | `web/static/app.js`, possibly `web/app.py` | #1, decision | Exporting an edited PDF page produces the corrected artifact, or the UI explains why not | M |
| 6 | P2 | M4B Phase 2 kickoff: user collects/annotates 10–20 privacy-cleared real docs; `documind-dataset` onboard; manual GT per annotation guide | `data/eval/real/` (git-ignored), templates | User provides documents | Dataset validates clean; manifests written; predictions generated | M (user-heavy) |
| 7 | P2 | First REAL evaluation run + report (provenance `real`) | `documind-eval`, `reports/` | #6 | `reports/real-baseline.md` with per-field/item CER/accuracy, explicit "first real numbers" caveat | S |
| 8 | P3 | Small-hygiene batch: wire/remove `MAX_OCR_JSON_BYTES` + `to_decimal`; explicit month table; CSV BOM decision; batch same-name keys; magic-sniff docstring | various | #1 | All P3s from §D closed or explicitly documented as accepted | S |
| 9 | P3 | M5C model decision experiment: `lang="vi"` vs `lang="en"` benchmark on a small VI sample set (local, CPU) | `ocr/engine.py`, benchmark harness | #6 (or a small VI sample set) | Measured comparison recorded in `reports/`; a pinned decision | M |

No time estimates are given beyond relative effort, per audit rules.

---

*End of audit report. Verification claims in this document reflect commands actually executed on 2026-10-26 against `feat/m5d-performance` @ d42ca6e plus this audit's working-tree changes.*
