---
name: web-api-and-frontend
description: Work on the DocuMind local web app (src/documind/web — FastAPI endpoints, service layer, static frontend) — use when changing endpoints, upload handling, exports, or the UI.
---

# Web API and frontend work

## Purpose

Keep the local web app secure, bounded, and contract-stable while it
evolves.

## When to use

- Changing endpoints, request/response schemas, upload validation,
  export kinds, or the static frontend.

## Relevant modules

- `src/documind/web/{app,service,schemas,pdf}.py`
- `src/documind/web/static/{index.html,app.js,style.css}`
- `docs/web-api.md` (normative API contract)
- `tests/test_web_api.py`, `tests/test_web_pdf_batch.py`

## Rules

- Service layer calls pipelines, never CLI subprocesses; inference goes
  through the shared locked engine.
- Uploads and export payloads are untrusted: validate size, extension,
  decoded content, dimensions, and payload bounds; test every rejection.
- Export kinds are contract: new kinds need read-back tests (JSON parse,
  CSV parse, XLSX open) and the formula-injection/filename policies.
- Frontend is vanilla JS with no build step; corrections must never
  mutate machine output in state; keyboard accessibility required.

## Workflow

1. Failing test first (mocked inference) for the new behavior.
2. Implement in the service layer; keep the endpoint thin.
3. Update `docs/web-api.md` in the same commit.
4. Smoke-test locally with `assets/samples/` inputs.

## Verification

```
python scripts/verify.py
pytest tests/test_web_api.py tests/test_web_pdf_batch.py -q
```

## Failure and rollback criteria

- Revert if an endpoint leaks internal errors, drops cleanup on any
  path, or changes a response contract without a doc update.
- Revert any CORS/auth/deployment scope creep.
