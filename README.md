# CodeCrew

A multi-agent AI system that turns a plain-language requirement into working, tested and documented code. Specialist agents (planner, test author, coder, debugger, reviewer) work under an orchestrator. A deterministic verifier stands between them and the user, so nothing is reported as passing unless it actually ran.

## How it works

```
requirement
   │
   ▼
Planner ──► spec: files, exact signatures, acceptance criteria (validated: safe paths, no cycles)
   │
   ▼
Test Author ──► unit tests written FROM THE SPEC, before any code exists (then locked)
   │
   ▼
Coder ──► implementation that must pass the locked tests
   │
   ▼
Verifier ──► syntax · cross-file contracts · spec conformance · ruff · bandit · sandboxed pytest / node:test
   │ fail                                                    │ pass (or debug limit reached)
   ▼                                                         ▼
Debugger ──► root-cause patch, or a test dispute       Reviewer ──► docstrings (AST-checked) + README
   │            (ruled on by the Test Author)                │
   └──► Verifier again; a round that makes things worse     ▼
        is reverted to the best version                    saved project + full run history
```

The orchestrator is a LangGraph state machine (`codecrew/orchestrator.py`). Change requests on an existing project start at **Triage**, which picks the minimal files to change and any new acceptance criteria. The project's saved spec and tests are re-run, so earlier behaviour is protected.

### What keeps results accurate

| Problem with single-shot AI coding | What CodeCrew does |
|---|---|
| Tests generated from buggy code "confirm" the bug | Tests come from the spec before the code exists. Only a dispute ruled on against the spec can change them. |
| The model claims success | Pass/fail comes only from real tools: Python AST, `node --check`, pytest/node:test JUnit XML, ruff and bandit. Anything not checkable is labelled *unchecked*. |
| Cross-file mismatches (wrong element IDs, missing imports) | Deterministic contract checks: HTML asset links, JS `getElementById` targets, Python imports and names, stdlib-shadowing filenames. |
| A "fix" that breaks something else | Every debug round is re-verified and scored; regressions are reverted. |
| Malformed model output slips through | All agent output is schema- or parser-validated. Invalid output is retried with the error fed back, never accepted. |
| Generated code can read your secrets or escape the folder | Tests run in a temp workspace with API keys stripped from the environment. Paths are normalised and `..`, absolute and hidden paths are rejected. Docker mode adds no network plus memory and PID limits. |

## Setup

Requirements: Python 3.10+, Node.js 20+ (also used to check and test generated JavaScript).

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # then add at least one API key
cd web && npm install && cd ..
```

Keys go in `.env`. `ANTHROPIC_API_KEY` (Claude) gives the most accurate results. `OPENROUTER_API_KEY` and `GEMINI_API_KEY` are free fallbacks, tried in order when the earlier provider is missing or rate-limited.

## Run

```bash
python scripts/dev.py            # API on :8000 (docs at /docs) + web UI on http://localhost:3000
```

Or run each part separately: `python server.py` and `cd web && npm run dev`.

Command line:

```bash
python cli.py "a module roman.py with to_roman(n) and from_roman(s) for 1..3999"
python cli.py --iterate <project-id> "also accept lowercase numerals"
```

Each generated project in `generated_projects/<id>/` contains its source, `tests/`, a `README.md` and `.codecrew/project.json` (spec, verification result, history). Run a project's tests with `python -m pytest`.

## Web UI (Next.js, `web/`)

- **Build**: describe a requirement and start a run.
- **Run view**: live pipeline, files as agents write them (with diffs between versions), the activity log, spec, per-test results, debug rounds (kept or reverted), test disputes and the README. Reconnecting resumes the stream without losing events.
- **Projects**: browse code, open a sandboxed live preview of web projects, request changes, download a zip.
- **Evaluation**: baseline vs CodeCrew benchmark results.
- **Settings**: provider order and model health.

TypeScript API types are generated from the backend's OpenAPI schema with `npm --prefix web run gen:api`.

## Tests and evaluation

```bash
python -m pytest tests           # offline: scripted LLM, real verifier, real pytest, real HTTP/SSE
python -m eval.run --check       # proves every benchmark's hidden tests pass on a reference solution
python -m eval.run               # single-agent baseline vs CodeCrew on hidden tests (calls real LLMs)
python -m eval.run --tasks roman,lru --modes codecrew
```

The benchmark (`eval/tasks.py`) has 15 tasks with hidden tests that neither system sees. Results are saved to `eval/results/` and shown on the Evaluation page. They include solve rate, hidden-test pass rate, LLM calls, time, and whether CodeCrew's own "verified" claim matched the hidden tests.

## Project layout

```
codecrew/            backend package
  orchestrator.py    LangGraph supervisor: routing, retry limit, best-version tracking
  agents/            planner, test_author, coder, debugger, reviewer, triage
  verify.py          deterministic verification
  sandbox.py         isolated test execution
  llm.py             provider chain (Anthropic → OpenRouter → Gemini), validation + corrective retry
  schemas.py         shared typed contracts (exported to the frontend via OpenAPI)
  store.py, runs.py  SQLite run/event store and live SSE fan-out
  projects.py        generated projects on disk
server.py            FastAPI app
cli.py               command-line entry point
web/                 Next.js frontend
eval/                benchmark tasks and runner
tests/               backend test suite
sandbox/Dockerfile   image for SANDBOX=docker
vscode-extension/    VS Code extension (still targets the v2 API; see Known limitations)
```

## Known limitations

- The default `process` sandbox strips secrets and enforces a timeout, but on Windows it has no memory or network limits. Use `SANDBOX=docker` for untrusted workloads.
- DOM and visual behaviour of web apps is checked statically (asset links, element IDs, structure). Only pure logic in separate JS modules is unit-tested.
- TypeScript files are reported as *unchecked*; there is no `tsc` step yet.
- Projects created before v3 have no spec, so they can be browsed but not iterated.
- The VS Code extension still calls the removed v2 endpoints and needs migrating to `/api/runs`.
