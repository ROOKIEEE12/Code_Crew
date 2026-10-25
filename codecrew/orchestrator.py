"""Orchestrator Agent: the supervisor graph that coordinates the specialists.

    build:   plan   -> write_tests -> code -> verify --fail--> debug -> verify ...
    iterate: triage -> write_tests -> code -> verify --fail--> debug -> verify ...
             verify --pass, or debug rounds exhausted--> review -> finalize

Routing is rule-based and enforced in code. The orchestrator keeps the best
verified version seen so far, so a debug round that makes things worse is
reverted instead of shipped.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from codecrew import projects
from codecrew.agents import coder, debugger, planner, reviewer, test_author, triage
from codecrew.config import settings
from codecrew.context import EventSink, RunCancelled, RunContext
from codecrew.schemas import DebugRound, FileSpec, RunState, Verification
from codecrew.verify import verify

SINGLE_CALL_MAX_FILES = 6


class _Flow(TypedDict, total=False):
    route: str


def _waves(files: list[FileSpec]) -> list[list[FileSpec]]:
    remaining = {f.path: f for f in files}
    done: set[str] = set()
    waves = []
    while remaining:
        wave = [f for f in remaining.values() if all(d in done or d not in remaining for d in f.depends_on)]
        wave = wave or list(remaining.values())
        waves.append(wave)
        for f in wave:
            done.add(f.path)
            del remaining[f.path]
    return waves


class Orchestrator:
    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.s = ctx.state
        self.best: Optional[tuple[tuple, dict[str, str], Verification]] = None
        self._existing_readme = ""

    # ------------------------------------------------------------ nodes

    def plan(self, _: _Flow) -> _Flow:
        self.ctx.phase("planning", "Planner is writing the technical specification")
        self.ctx.step("Orchestrator", "Routing requirement to the Planner Agent.")
        spec = planner.plan(self.ctx, self.s.requirement)
        self.s.spec = spec
        self.ctx.step("Planner", f"Spec '{spec.project_name}': {len(spec.files)} file(s), "
                                 f"{len(spec.acceptance_criteria)} acceptance criteria.")
        self.ctx.emit("spec", spec.model_dump())
        return {}

    def triage(self, _: _Flow) -> _Flow:
        self.ctx.phase("triage", "Orchestrator is deciding which agents and files the change needs")
        t = triage.triage(self.ctx, self.s.spec, self.s.files, self.s.requirement)
        self.s.triage = t
        spec = self.s.spec
        by_path = {f.path: f for f in spec.files}
        for f in t.files:
            by_path[f.path] = f
        spec.files = list(by_path.values())
        spec.acceptance_criteria += t.new_acceptance_criteria
        self.ctx.step("Orchestrator", f"Triage ({t.intent}): {t.explanation} "
                                      f"Files: {', '.join(f.path for f in t.files) or 'none'}.")
        self.ctx.emit("triage", t.model_dump())
        self.ctx.emit("spec", spec.model_dump())
        return {}

    def write_tests(self, _: _Flow) -> _Flow:
        spec = self.s.spec
        if self.s.mode == "iterate":
            new = self.s.triage.new_acceptance_criteria if self.s.triage else []
            if not new or not any(f.testable for f in spec.files):
                return {}
            self.ctx.phase("testing", "Test Author is adding tests for the new acceptance criteria")
            added = test_author.write_tests(self.ctx, spec, criteria=new, existing=self.s.tests)
        else:
            if not any(f.testable for f in spec.files):
                self.ctx.step("Test Author", "No testable logic in this spec; relying on static and contract checks.")
                return {}
            self.ctx.phase("testing", "Test Author is writing tests from the spec (before any code)")
            added = test_author.write_tests(self.ctx, spec)
            uncovered = test_author.uncovered_criteria(spec, added)
            if uncovered:
                self.ctx.step("Test Author", f"Adding tests for uncovered criteria: {', '.join(uncovered)}.")
                missing = [ac for ac in spec.acceptance_criteria if ac.id in uncovered]
                added.update(test_author.write_tests(self.ctx, spec, criteria=missing, existing=added))
        self.s.tests.update(added)
        self.ctx.step("Test Author", f"Wrote {len(added)} test file(s): {', '.join(added)}.")
        for path, code in added.items():
            self.ctx.emit("file", {"path": path, "content": code, "kind": "test", "by": "Test Author"})
        return {}

    def code(self, _: _Flow) -> _Flow:
        spec = self.s.spec
        self.ctx.phase("coding", "Coder is implementing the spec")
        if self.s.mode == "iterate":
            assigned = self.s.triage.files if self.s.triage else []
            if not assigned:
                return {}
            instructions = f"{self.s.requirement}\n\n{self.s.triage.instructions}"
            out = coder.generate(self.ctx, spec, assigned, self.s.files, self.s.tests, instructions)
            self._apply(out, "Coder")
            return {}

        if len(spec.files) <= SINGLE_CALL_MAX_FILES:
            self.ctx.step("Code Generation", f"Writing all {len(spec.files)} file(s) in one consistent pass.")
            self._apply(coder.generate(self.ctx, spec, spec.files, {}, self.s.tests), "Coder")
            return {}

        waves = _waves(spec.files)
        for i, wave in enumerate(waves, 1):
            self.ctx.check_cancelled()
            self.ctx.step("Code Generation", f"Wave {i}/{len(waves)}: {', '.join(f.path for f in wave)} in parallel.")

            def job(fs: FileSpec) -> dict[str, str]:
                deps = {d: self.s.files[d] for d in fs.depends_on if d in self.s.files}
                return coder.generate(self.ctx, spec, [fs], deps, self.s.tests)

            with ThreadPoolExecutor(max_workers=settings.max_parallel_workers) as pool:
                for out in pool.map(job, wave):
                    self._apply(out, "Coder")
        return {}

    def verify(self, _: _Flow) -> _Flow:
        self.ctx.phase("verifying", "Running syntax, contract, lint/security checks and the test suite")
        v = verify({**self.s.files, **self.s.tests}, self.s.spec)
        score = v.score()
        rnd = self.s.debug_rounds[-1] if self.s.debug_rounds else None

        if self.best is None or score >= self.best[0]:
            self.best = (score, dict(self.s.files), v)
            self.s.best_round = len(self.s.debug_rounds)
            if rnd:
                rnd.score_after, rnd.kept = list(score), True
        else:
            # This round made things worse: revert to the best version.
            if rnd:
                rnd.score_after, rnd.kept = list(score), False
            self.ctx.step("Orchestrator", f"Round {rnd.round if rnd else '?'} regressed ({v.summary}); reverting to the best version.")
            self.s.files = dict(self.best[1])
            for path, content in self.s.files.items():
                self.ctx.emit("file", {"path": path, "content": content, "kind": "source", "by": "Orchestrator (revert)"})
            v = self.best[2]

        self.s.verification = v
        self.ctx.step("Verifier", ("PASSED: " if v.passed else "FAILED: ") + v.summary)
        self.ctx.emit("verification", {"round": len(self.s.debug_rounds), **v.model_dump()})
        if rnd:
            self.ctx.emit("debug_round", rnd.model_dump())

        if v.passed:
            return {"route": "review"}
        if len(self.s.debug_rounds) >= settings.max_debug_rounds:
            self.ctx.step("Orchestrator", f"Debug round limit ({settings.max_debug_rounds}) reached; "
                                          "keeping the best verified version and reporting remaining issues.")
            return {"route": "review"}
        return {"route": "debug"}

    def debug(self, _: _Flow) -> _Flow:
        n = len(self.s.debug_rounds) + 1
        self.ctx.phase("debugging", f"Debugger round {n}")
        v = self.s.verification
        issues = sorted(v.issues, key=lambda i: (i.severity != "error", i.source == "lint"))
        self.ctx.step("Debugging", f"Round {n}: analysing {sum(1 for i in issues if i.severity == 'error')} error(s).")
        changed, disputes = debugger.debug(self.ctx, self.s.spec, self.s.files, self.s.tests, issues, self.s.debug_rounds)

        rnd = DebugRound(round=n, targeted_issues=len(issues), changed_files=list(changed),
                         disputes=list(disputes), score_before=list(v.score()))
        self.s.debug_rounds.append(rnd)
        self._apply(changed, "Debugger")
        if changed:
            self.ctx.step("Debugging", f"Patched {', '.join(changed)}.")
        if disputes:
            self._resolve_disputes(disputes)
        return {}

    def review(self, _: _Flow) -> _Flow:
        spec = self.s.spec
        self.ctx.phase("documenting", "Reviewer is writing docs")
        if self.best and self.s.verification is not self.best[2] and self.best[0] > self.s.verification.score():
            self.s.files, self.s.verification = dict(self.best[1]), self.best[2]

        documented = reviewer.add_docstrings(self.ctx, self.s.files)
        if documented:
            self._apply(documented, "Reviewer")
            self.ctx.step("Review", f"Added docstrings to {', '.join(documented)} (verified behaviour-neutral via AST).")

        wants_readme = self.s.mode == "build" or not self._existing_readme or (self.s.triage and self.s.triage.update_readme)
        if wants_readme:
            self.s.readme = reviewer.write_readme(self.ctx, spec, self.s.files, self.s.tests, self.s.verification)
            self.ctx.emit("readme", {"content": self.s.readme})
            self.ctx.step("Review", "README.md written.")
        else:
            self.s.readme = self._existing_readme
        return {}

    def finalize(self, _: _Flow) -> _Flow:
        spec = self.s.spec
        if not self.s.project_id:
            self.s.project_id = projects.new_project_id(spec.project_name)
        root = projects.save(self.s.project_id, spec, self.s.files, self.s.tests, self.s.readme,
                             self.s.verification, self.s.id, self.s.requirement)
        self.s.project_dir = str(root)
        self.ctx.step("Orchestrator", f"Saved project '{self.s.project_id}'.")
        return {}

    # ------------------------------------------------------------ helpers

    def _apply(self, changed: dict[str, str], by: str) -> None:
        for path, content in changed.items():
            self.s.files[path] = content
            self.ctx.emit("file", {"path": path, "content": content, "kind": "source", "by": by})

    def _resolve_disputes(self, disputes: dict[str, str]) -> None:
        for test_id, reason in disputes.items():
            if self.s.disputes_used >= settings.max_test_disputes:
                self.ctx.step("Orchestrator", "Test dispute limit reached; remaining disputes ignored.")
                return
            test_path = test_id.split("::", 1)[0]
            if test_path not in self.s.tests:
                continue
            self.s.disputes_used += 1
            wrong, explanation, fixed = test_author.review_dispute(
                self.ctx, self.s.spec, test_path, self.s.tests[test_path], test_id, reason)
            self.ctx.emit("dispute", {"test_id": test_id, "reason": reason, "upheld": wrong, "explanation": explanation})
            if wrong:
                self.s.tests.update(fixed)
                self.best = None  # the test suite changed, so earlier scores are not comparable
                self.ctx.step("Test Author", f"Dispute upheld for {test_id}: test corrected to match the spec.")
                self.ctx.emit("file", {"path": test_path, "content": fixed[test_path], "kind": "test", "by": "Test Author"})
            else:
                self.ctx.step("Test Author", f"Dispute rejected for {test_id}: the test matches the spec.")

    # ------------------------------------------------------------ graph

    def graph(self):
        g = StateGraph(_Flow)
        for name in ("plan", "triage", "write_tests", "code", "verify", "debug", "review", "finalize"):
            g.add_node(name, self._guard(getattr(self, name)))
        g.add_conditional_edges(START, lambda _: "triage" if self.s.mode == "iterate" else "plan", ["plan", "triage"])
        g.add_edge("plan", "write_tests")
        g.add_edge("triage", "write_tests")
        g.add_edge("write_tests", "code")
        g.add_edge("code", "verify")
        g.add_conditional_edges("verify", lambda f: f["route"], ["debug", "review"])
        g.add_edge("debug", "verify")
        g.add_edge("review", "finalize")
        g.add_edge("finalize", END)
        return g.compile()

    def _guard(self, fn: Callable[[_Flow], _Flow]) -> Callable[[_Flow], _Flow]:
        def wrapped(flow: _Flow) -> _Flow:
            self.ctx.check_cancelled()
            return fn(flow)
        return wrapped

    def run(self) -> RunState:
        s = self.s
        s.status = "running"
        self.ctx.emit("status", {"status": s.status})
        try:
            if s.mode == "iterate":
                loaded = projects.load(s.project_id)
                if not loaded["spec"]:
                    raise ValueError("This project was created by an older CodeCrew version and has no spec; rebuild it to iterate.")
                s.spec, s.files, s.tests = loaded["spec"], loaded["files"], loaded["tests"]
                self._existing_readme = loaded["readme"]
                self.ctx.step("Orchestrator", f"Loaded '{s.project_id}': {len(s.files)} source file(s), {len(s.tests)} test file(s).")
            self.graph().invoke({}, {"recursion_limit": 8 + 2 * settings.max_debug_rounds + 4})
            s.status = "succeeded" if s.verification and s.verification.passed else "failed"
        except RunCancelled:
            s.status = "cancelled"
            self.ctx.step("Orchestrator", "Run cancelled.")
        except Exception as e:  # surfaced to the UI; the run record keeps the message
            s.status, s.error = "error", f"{type(e).__name__}: {e}"
            self.ctx.step("Orchestrator", f"Run failed: {s.error}")
        s.finished_at = time.time()
        s.phase = "done"
        self.ctx.emit("done", {
            "status": s.status,
            "error": s.error,
            "project_id": s.project_id,
            "summary": s.verification.summary if s.verification else None,
            "usage": s.usage.model_dump(),
        })
        return s


def new_run(requirement: str, mode: str = "build", project_id: Optional[str] = None) -> RunState:
    return RunState(id=uuid.uuid4().hex[:12], mode=mode, requirement=requirement.strip(), project_id=project_id)


def run_sync(state: RunState, sink: Optional[EventSink] = None, log: Optional[Callable[[str], None]] = None) -> RunState:
    return Orchestrator(RunContext(state, sink, log)).run()


def mermaid() -> str:
    """The orchestration graph as Mermaid, for docs and the UI."""
    return Orchestrator(RunContext(new_run("x"))).graph().get_graph().draw_mermaid()
