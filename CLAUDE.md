# Foreman TODO API

A minimal FastAPI-based TODO API, built end-to-end by the [foreman](https://github.com/herbae-org/foreman) AI Factory pipeline as a demonstration that the four-body-agent system (Planner, Implementer, Fixer, Merger) can ship a working backend without human-in-the-loop beyond the `plan` label and high-risk spec PR review.

## Scope

- HTTP JSON API for managing TODO items (`id`, `title`, `done`, `created_at`).
- Endpoints: `GET /health`, `POST /todos`, `GET /todos`, `GET /todos/{id}`, `PATCH /todos/{id}`, `DELETE /todos/{id}`.
- Persistence: SQLite via `sqlite3` stdlib (no ORM).
- Tests: `pytest` with `httpx` client; every endpoint must have happy-path + one failure-path test.

## Stack

- **Language:** Python 3.11+ (runner default on `ubuntu-latest`).
- **Framework:** `fastapi[standard]` (includes `uvicorn`).
- **Testing:** `pytest`, `httpx` (fastapi's `TestClient` is fine too).
- **Packaging:** `pyproject.toml` with `[project.optional-dependencies] dev = ["pytest", "httpx"]`. No `setup.py`, no `requirements.txt`.
- **Runtime dependencies:** only `fastapi[standard]`. Keep the list tight.

## Non-goals

- No UI, no templates, no static files.
- No auth, no rate limiting, no CORS config.
- No Docker, no `Dockerfile`, no CI beyond what the AI Factory provides.
- No ORM (SQLAlchemy is overkill).
- No migrations tool (Alembic is overkill).
- No async DB driver. `sqlite3` + `with ... as conn:` is fine.

## Architecture

Single package `src/todo_api/` with at most three modules:

- `src/todo_api/app.py` — FastAPI app, route handlers.
- `src/todo_api/db.py` — SQLite connection + schema init + CRUD helpers.
- `src/todo_api/__init__.py` — empty, just marks the package.

Tests mirror structure under `tests/`.

## Coding conventions

- **Type hints** on every function signature.
- **Pydantic v2** models for request/response bodies (`model_config = {"from_attributes": True}` if needed).
- **Small functions.** No function over ~20 lines.
- **Error handling at boundaries only.** Don't wrap internal calls in try/except "just in case."
- **No comments** explaining what well-named code already does. Save comments for WHY.
- **Snake_case** everywhere Python allows it; PEP8 is the target.

## Testing expectations

- Every PR must land with passing `pytest` runs.
- New endpoints must ship with tests in the same PR.
- Don't mock the database — hit a real SQLite file in a tmpdir fixture.
- Coverage is not enforced, but aim for every code path in handlers to be hit by at least one test.

## How this repo is built

The [foreman](https://github.com/herbae-org/foreman) AI Factory drives everything:

1. A maintainer opens an issue using the `Plannable feature` template, labels it `plan`.
2. `[AUTOAGENT] Planner` classifies risk, posts a change-set as a comment.
3. For low/medium risk: `[AUTOAGENT] Implementer` is dispatched automatically. For high risk: a spec PR opens under `docs/change-sets/${N}.md` and waits for a human to merge.
4. The Implementer reads the change-set, codes, runs tests, opens a PR.
5. `[AUTOAGENT] Fixer` reacts to failing CI if any.
6. `[AUTOAGENT] Merger` (on cron or manual dispatch) merges green PRs.
7. `[AUTOAGENT] Board Sync` advances the Projects V2 card through Todo → In Progress → Ready For QA → Done.

The pipeline's config lives in `.github/autoagent-config.yml`. The prompts live in `.github/prompts/`. The workflows live in `.github/workflows/`. All of it is inherited from the foreman fork; don't edit them in this repo unless you're changing pipeline behaviour specifically for TODO API.
