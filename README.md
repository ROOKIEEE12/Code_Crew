# CodeCrew

A multi-agent AI system that turns a plain-language requirement into working, tested and documented code. Specialist agents (planner, test author, coder, debugger, reviewer) work under an orchestrator. A deterministic verifier stands between them and the user, so nothing is reported as passing unless it actually ran.

## How it works

```
requirement  (+ links it mentions are read; + reference screenshots you attach)
   │
   ▼
Planner ──► spec: files, exact signatures, acceptance criteria, and for web pages a design
            brief: sections with ids and real content, palette, type, interactions
   │
   ▼
Test Author ──► unit tests written FROM THE SPEC, before any code exists (then locked)
   │
   ▼
Coder ──► implementation that must pass the locked tests
   │
   ▼
Verifier ──► syntax · cross-file contracts · spec conformance · web quality · headless browser
   │          · ruff · bandit · sandboxed pytest / node:test
   │ fail                                                    │ pass (or debug limit reached)
   ▼                                                         ▼
Debugger ──► root-cause patch, or a test dispute       Reviewer ──► web pages: looks at desktop and phone
   │            (ruled on by the Test Author)                │       screenshots, scores them against the
   └──► Verifier again; a round that makes things worse     │       brief and references; the Coder polishes
        is reverted to the best version                    │       (kept only if every check still passes)
                                                             ▼
                                                     docstrings (AST-checked) + README → saved project
```

The orchestrator is a LangGraph state machine (`codecrew/orchestrator.py`). Change requests on an existing project start at **Triage**, which picks the minimal files to change and any new acceptance criteria. The project's saved spec and tests are re-run, so earlier behaviour is protected.

### What keeps results accurate

| Problem with single-shot AI coding | What CodeCrew does |
|---|---|
| Tests generated from buggy code "confirm" the bug | Tests come from the spec before the code exists. Only a dispute ruled on against the spec can change them. |
| The model claims success | Pass/fail comes only from real tools: Python AST, `node --check`, pytest/node:test JUnit XML, ruff and bandit. Anything not checkable is labelled *unchecked*. |
| Cross-file mismatches (wrong element IDs, missing imports) | Deterministic contract checks: HTML asset links, JS `getElementById` targets, Python imports and names, stdlib-shadowing filenames. |
| A "fix" that breaks something else | Every debug round is re-verified and scored; regressions are reverted. |
| "Make it like this site" is ignored, or the page comes out bare | Links in the request are fetched (and screenshotted in a headless browser); a site that blocks readers is reported, never guessed. The Planner writes a design brief, the Coder follows design rules, and the verifier fails a page that is missing a planned section, shows placeholder text, has no viewport or responsive CSS, throws a JavaScript error or scrolls sideways on a phone. |
| Tests pass but the page looks wrong | A vision model reviews screenshots of the finished page against the brief and your references, and the Coder applies its fixes. |
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

Each role can use its own models (`ANTHROPIC_MODEL_CODER`, `GEMINI_MODELS_PLANNER`, ...; see `.env.example`): put the strongest model on the planner, coder, debugger and design review, and a cheaper one on the reviewer and clarifier. Free "flash" models work, but large, polished websites need a strong model.

Optional but recommended for web projects (browser checks, reference screenshots, design review):

```bash
pip install playwright
python -m playwright install chromium
```

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

- **Build**: describe a requirement and start a run. With "Let the crew ask me questions first" on, the Planner may ask up to 2 multiple-choice questions before planning; an unanswered question uses its recommended option after `QUESTION_TIMEOUT_SEC`.
- **Run view**:
  - **The crew**: one face per agent (or a minimal style) with a baton showing who is working. Hover a face for its model, AI calls, time and status. A live meter shows time, AI calls, tokens and tests.
  - **Live tab**: the code typing in as agents write it, lines blamed by a failed check in red, a fix's changed lines flashing green, and tests ticking off as their real results arrive.
  - **Crew transcript**: a plan checklist that ticks itself off, agent messages, "Thinking…" turning into "Thought for Ns" (with the Planner's assumptions and the Debugger's diagnosis), hand-offs, one card per real check the Verifier ran (syntax, cross-file links, lint and security, tests) with its output, and file edits with lines added and removed.
  - **Steer mid-run**: type an instruction while the crew works; every later agent receives it, and the transcript shows which agent picked it up first.
  - A "Verified" stamp and confetti when you watch a run pass, and optional sound effects (off by default).
  - Code (with diffs between versions), test results, debug rounds (kept or reverted), test disputes, plan and README tabs. Reconnecting resumes the stream without losing events.
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
  agents/            planner, test_author, coder, debugger, reviewer, design_reviewer, triage
  verify.py          deterministic verification (incl. web quality and browser checks)
  reference.py       reads links in a request (reference websites)
  render.py          headless Chromium: page checks and screenshots
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

## When free AI models misbehave

Free models are often slow, rate-limited, or occasionally hang. CodeCrew guards against that:

- **Time limit per request** (`LLM_TIMEOUT_SEC`, default 300 s) on every provider, plus a watchdog in case a client library ignores its own timeout. A model that stops responding is cooled down and the next one is tried.
- **Bad models are set aside**: a model that times out or keeps returning unusable output is skipped for the rest of the run (`MODEL_STRIKES`).
- **Shared rate limits are waited out**: if every model is cooling down at once, the run waits (up to `MAX_MODEL_WAIT_SEC`) instead of failing.
- **Stop works immediately**, even in the middle of a slow AI call.
- **Nothing finished is lost**: parallel files are saved the moment each is ready, and a run that stopped (error, Stop, or a backend restart) shows a **Resume** button. Resume keeps the plan, your answers and instructions, the locked tests and every finished file, and continues from the first unfinished step (`POST /api/runs/{id}/resume`).

## Known limitations

- The default `process` sandbox strips secrets and enforces a timeout, but on Windows it has no memory or network limits. Use `SANDBOX=docker` for untrusted workloads.
- Only pure logic in separate JS modules is unit-tested. Pages are opened in a headless browser (JavaScript errors, phone layout, sections) when Playwright is installed, but clicks and other interactions are not exercised.
- Some sites (for example ones behind Cloudflare) block automated readers. CodeCrew then says it could not read the link; attach a screenshot instead.
- The design review needs a model that can see images (Claude or Gemini; many free OpenRouter models cannot). Without one, it is skipped and the run says so.
- TypeScript files are reported as *unchecked*; there is no `tsc` step yet.
- Projects created before v3 have no spec, so they can be browsed but not iterated.
- The VS Code extension still calls the removed v2 endpoints and needs migrating to `/api/runs`.
