"""Orchestrator Agent: the supervisor graph that coordinates the specialists.

    build:   plan   -> write_tests -> code -> verify --fail--> debug -> verify ...
    iterate: triage -> write_tests -> code -> verify --fail--> debug -> verify ...
             verify --pass, web page--> design_review --fixes--> (Coder polish) verify
             verify --pass, or debug rounds exhausted--> review -> finalize

Links in the request are read before planning (reference.py), and images
the user attached go to vision-capable models for the plan and the code.

Routing is rule-based and enforced in code. The orchestrator keeps the best
verified version seen so far, so a debug round that makes things worse is
reverted instead of shipped.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from codecrew import llm, projects, reference, render
from codecrew.agents import clarifier, coder, debugger, design_reviewer, planner, reviewer, test_author, triage
from codecrew.config import settings
from codecrew.context import EventSink, RunCancelled, RunContext
from codecrew.schemas import Clarification, DebugRound, DesignReview, FileSpec, RunState, Verification
from codecrew.verify import verify, web_pages

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
        self._pending: Optional[str] = None  # what the next verify is checking: "debug" or "polish"
        self._verifies = 0
        self._design_rounds = 0

    # ------------------------------------------------------------ nodes

    def plan(self, _: _Flow) -> _Flow:
        if self.s.spec is not None:  # resumed run: the plan is already agreed
            self.ctx.step("Orchestrator", f"Resuming with the saved plan '{self.s.spec.project_name}'.")
            return {}
        self.ctx.phase("planning", "Planner is writing the technical specification")
        self._read_references(self.s.requirement)
        self.ctx.step("Orchestrator", "Routing requirement to the Planner Agent.")
        requirement = self._clarify(self.s.requirement)
        spec = planner.plan(self.ctx, requirement, self._references(), self.ctx.reference_images)
        self.s.spec = spec
        self.ctx.thought("Planner", [
            f"{len(spec.files)} file(s): {', '.join(f.path for f in spec.files)}.",
            f"{len(spec.acceptance_criteria)} things that must be true when it's done.",
            *spec.assumptions,
        ])
        if spec.design:
            self.ctx.thought("Planner", [
                f"Design: {spec.design.style}",
                "Sections: " + ", ".join(sec.name for sec in spec.design.sections) + ".",
                "Palette: " + ", ".join(c.hex for c in spec.design.palette) + ".",
            ])
        self.ctx.step("Planner", f"Spec '{spec.project_name}': {len(spec.files)} file(s), "
                                 f"{len(spec.acceptance_criteria)} acceptance criteria"
                                 + (f", {len(spec.design.sections)} designed section(s)." if spec.design else "."))
        self.ctx.emit("spec", spec.model_dump())
        return {}

    def _clarify(self, requirement: str) -> str:
        """Asks the user about open choices before planning, when enabled."""
        if not self.s.ask_questions:
            return requirement
        if len(requirement) >= settings.clarify_max_chars:
            self.ctx.step("Planner", "The request is detailed enough; no questions needed.")
            return requirement
        self.ctx.phase("planning", "Planner is checking whether anything is unclear")
        context = requirement
        if self.s.references or self.ctx.reference_images:
            context += (f"\n\n(The user gave {len(self.s.references)} reference link(s) and "
                        f"{len(self.ctx.reference_images)} reference image(s), so the look is already decided.)")
        try:
            out = clarifier.questions(self.ctx, context)
        except RunCancelled:
            raise
        except Exception as e:  # questions are a nicety; never fail the build over them
            self.ctx.step("Planner", f"Skipped questions ({type(e).__name__}); planning with sensible defaults.")
            return requirement
        if not out.questions:
            self.ctx.step("Planner", "The request is clear; no questions needed.")
            return requirement
        answers = []
        for q in out.questions:
            labels = [o.label for o in q.options]
            rec = next(i for i, o in enumerate(q.options) if o.recommended)
            self.ctx.phase("planning", "Planner has a question for you")
            choice, auto = self.ctx.ask("Planner", q.question, q.why, labels, rec, settings.question_timeout_sec)
            answers.append((q.question, labels[choice], auto))
            self.s.clarifications.append(Clarification(question=q.question, answer=labels[choice], auto=auto))
        self.ctx.phase("planning", "Planner is writing the technical specification")
        self.ctx.step("Planner", "Planning with your answers: " + "; ".join(f"{a}" for _, a, _ in answers) + ".")
        return clarifier.with_answers(requirement, answers)

    def triage(self, _: _Flow) -> _Flow:
        self.ctx.phase("triage", "Orchestrator is deciding which agents and files the change needs")
        self._read_references(self.s.requirement)
        t = triage.triage(self.ctx, self.s.spec, self.s.files, self.s.requirement, self._references(),
                          self.ctx.reference_images)
        self.s.triage = t
        spec = self.s.spec
        if t.design:
            spec.design = t.design
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
        elif self.s.tests:  # resumed run: the tests were already written and locked
            self.ctx.step("Test Author", f"Keeping the {len(self.s.tests)} test file(s) already written: {', '.join(self.s.tests)}.")
            return {}
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
        if self.s.mode == "build":
            self.ctx.thought("Test Author", [
                "Tests come from the plan, before any code exists.",
                "Tests cover acceptance criteria " + ", ".join(
                    ac.id for ac in spec.acceptance_criteria if ac.verification == "automated_test") + ".",
            ])
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
            out = coder.generate(self.ctx, spec, assigned, self.s.files, self.s.tests, instructions,
                                 self._references(), self.ctx.reference_images)
            self._apply(out, "Coder")
            return {}

        todo = [f for f in spec.files if f.path not in self.s.files]
        if not todo:
            return {}
        if self.s.files:  # resumed run: keep the files already written, write only the rest
            self.ctx.step("Code Generation", f"Keeping {len(self.s.files)} file(s) already written; "
                                             f"{len(todo)} left: {', '.join(f.path for f in todo)}.")
        elif len(todo) <= SINGLE_CALL_MAX_FILES:
            self.ctx.step("Code Generation", f"Writing all {len(todo)} file(s) in one consistent pass.")
            self._apply(coder.generate(self.ctx, spec, todo, {}, self.s.tests, "", self._references(),
                                       self.ctx.reference_images), "Coder")
            return {}

        waves = _waves(todo)
        for i, wave in enumerate(waves, 1):
            self.ctx.check_cancelled()
            self.ctx.step("Code Generation", f"Wave {i}/{len(waves)}: {', '.join(f.path for f in wave)} in parallel.")

            def job(fs: FileSpec) -> dict[str, str]:
                deps = {d: self.s.files[d] for d in fs.depends_on if d in self.s.files}
                return coder.generate(self.ctx, spec, [fs], deps, self.s.tests, "", self._references(),
                                      self.ctx.reference_images)

            pool = ThreadPoolExecutor(max_workers=settings.max_parallel_workers)
            try:
                # Save each file the moment it is ready, so a slow file never holds
                # finished ones hostage and a stopped run keeps everything done so far.
                for future in as_completed([pool.submit(job, fs) for fs in wave]):
                    self._apply(future.result(), "Coder")
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        return {}

    def verify(self, _: _Flow) -> _Flow:
        self.ctx.phase("verifying", "Running syntax, contract, quality, browser and test checks")
        rnd_no = len(self.s.debug_rounds)
        self._verifies += 1
        vid = self._verifies
        pending, self._pending = self._pending, None
        v = verify({**self.s.files, **self.s.tests}, self.s.spec,
                   progress=lambda p: self.ctx.emit("tool", {"id": f"v{vid}-{p['key']}", "round": rnd_no, **p}))
        score = v.score()
        rnd = self.s.debug_rounds[-1] if pending == "debug" and self.s.debug_rounds else None

        if self.best is None or score >= self.best[0]:
            self.best = (score, dict(self.s.files), v)
            self.s.best_round = len(self.s.debug_rounds)
            if rnd:
                rnd.score_after, rnd.kept = list(score), True
        else:
            # This round made things worse: revert to the best version.
            if rnd:
                rnd.score_after, rnd.kept = list(score), False
            if pending == "polish" and self.s.design_reviews:
                self.s.design_reviews[-1].kept = False
                self.ctx.emit("design_review", self.s.design_reviews[-1].model_dump())
                self.ctx.step("Orchestrator", f"The design polish broke a check ({v.summary}); keeping the version from before it.")
            else:
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
            return {"route": "design_review" if self._design_review_due() else "review"}
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
        changed, disputes, notes = debugger.debug(self.ctx, self.s.spec, self.s.files, self.s.tests, issues, self.s.debug_rounds)
        self.ctx.thought("Debugger", notes)

        rnd = DebugRound(round=n, targeted_issues=len(issues), changed_files=list(changed),
                         disputes=list(disputes), score_before=list(v.score()))
        self.s.debug_rounds.append(rnd)
        self._pending = "debug"
        self._apply(changed, "Debugger")
        if changed:
            self.ctx.step("Debugging", f"Patched {', '.join(changed)}.")
        if disputes:
            self._resolve_disputes(disputes)
        return {}

    def _design_review_due(self) -> bool:
        if self._design_rounds >= settings.design_review_rounds or not web_pages(self.s.files):
            return False
        if self.s.mode == "iterate":  # only when the change touched how the page looks
            changed = [f.path for f in self.s.triage.files] if self.s.triage else []
            return any(p.endswith((".html", ".css")) for p in changed)
        return True

    def design_review(self, _: _Flow) -> _Flow:
        """Screenshots the finished page; a vision model compares it with the design brief
        and the references, and the Coder polishes. Kept only if every check still passes."""
        self._design_rounds += 1
        n = self._design_rounds
        if not render.available():
            self.ctx.step("Reviewer", f"Skipped the visual design review: {render.unavailable_reason()}.")
            return {"route": "review"}
        self.ctx.phase("documenting", "Reviewer is looking at the finished page")
        source = {p: c for p, c in self.s.files.items()}
        try:
            reports = render.check_pages(source, web_pages(source)[:2], screenshots=True)
        except Exception as e:  # a browser problem should not cost the user the build
            self.ctx.step("Reviewer", f"Skipped the visual design review: the page could not be opened ({type(e).__name__}).")
            return {"route": "review"}
        shots: list[tuple[str, bytes]] = []
        ids: list[int] = []
        for r in reports:
            for label in ("desktop", "phone"):
                if label in r.screenshots:
                    shots.append((f"{r.page} on a {label}", r.screenshots[label]))
                    saved = self.ctx.save_image("screenshot", f"{r.page} · {label}", "image/jpeg", r.screenshots[label])
                    if saved:
                        ids.append(saved.id)
        if ids:
            self.ctx.emit("image", {"ids": ids, "agent": "Reviewer", "caption": "Screenshots the Reviewer looked at"})
        try:
            out = design_reviewer.review(self.ctx, self.s.spec, shots[:4], self._references(), self.ctx.reference_images[:3])
        except RunCancelled:
            raise
        except llm.LLMError as e:
            self.ctx.step("Reviewer", "Skipped the visual design review: no available model could look at the "
                                      f"screenshots ({str(e).splitlines()[0][:120]}).")
            return {"route": "review"}
        record = DesignReview(round=n, score=out.score, strengths=out.strengths, fixes=out.fixes, screenshots=ids)
        self.s.design_reviews.append(record)
        self.ctx.thought("Reviewer", [f"Design score {out.score}/10.", *out.strengths[:1], *out.fixes[:3]])
        if out.score >= settings.design_review_pass or not out.fixes:
            self.ctx.step("Reviewer", f"Design review: {out.score}/10, ready to ship.")
            self.ctx.emit("design_review", record.model_dump())
            return {"route": "review"}

        spec = self.s.spec
        visual = [f for f in spec.files if f.path.endswith((".html", ".css")) or (f.path.endswith(".js") and not f.testable)]
        self.ctx.step("Reviewer", f"Design review: {out.score}/10. Sending {len(out.fixes)} visual fix(es) to the Coder.")
        self.ctx.phase("coding", "Coder is polishing the design")
        instructions = ("Design review fixes. Apply every one; keep all section ids, content, scripts and behaviour "
                        "that already work:\n" + "\n".join(f"- {fix}" for fix in out.fixes))
        try:
            polished = coder.generate(self.ctx, spec, visual, self.s.files, self.s.tests, instructions,
                                      self._references(), self.ctx.reference_images)
        except RunCancelled:
            raise
        except llm.LLMError as e:
            self.ctx.step("Coder", f"Could not apply the design fixes ({str(e).splitlines()[0][:120]}); keeping the tested version.")
            self.ctx.emit("design_review", record.model_dump())
            return {"route": "review"}
        record.applied = True
        self.ctx.emit("design_review", record.model_dump())
        self._apply(polished, "Coder")
        self._pending = "polish"
        return {"route": "verify"}

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

    def _read_references(self, text: str) -> None:
        """Reads the links in the request once; what they contain goes to the agents."""
        urls = reference.find_urls(text)
        if not urls or self.s.references or not settings.read_links:
            return
        self.ctx.phase(self.s.phase, "Reading the links you gave")
        for i, url in enumerate(urls):
            self.ctx.check_cancelled()
            tool = {"id": f"ref-{i}", "round": 0, "key": "reference", "label": "Read the link you gave", "cmd": url}
            self.ctx.emit("tool", {**tool, "status": "running"})
            ref, shot = reference.read(url)
            self.s.references.append(ref)
            if shot:
                self.ctx.reference_images.append(("image/jpeg", shot))
                self.ctx.save_image("reference", f"Screenshot of {url}", "image/jpeg", shot)
            if ref.ok:
                found = [f"{len(ref.outline)} outline item(s)", f"{len(ref.colors)} colour(s)" if ref.colors else "",
                         "a screenshot" if shot else ""]
                self.ctx.emit("tool", {**tool, "status": "ok", "result": ", ".join(x for x in found if x),
                                       "output": reference.brief([ref])[:2500]})
                self.ctx.step("Orchestrator", f"Read {url}: '{ref.title or 'untitled'}'"
                                              + (", with a screenshot for the designers." if shot else "."))
            else:
                self.ctx.emit("tool", {**tool, "status": "bad", "result": "could not read it", "output": ref.error})
                self.ctx.step("Orchestrator", f"Could not read {url} ({ref.error}). The crew will not guess what it "
                                              "shows; attach a screenshot of it if the look matters.")
        self.ctx.emit("references", {"references": [r.model_dump() for r in self.s.references]})

    def _references(self) -> str:
        return reference.brief(self.s.references)

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
        for name in ("plan", "triage", "write_tests", "code", "verify", "debug", "design_review", "review", "finalize"):
            g.add_node(name, self._guard(getattr(self, name)))
        g.add_conditional_edges(START, lambda _: "triage" if self.s.mode == "iterate" else "plan", ["plan", "triage"])
        g.add_edge("plan", "write_tests")
        g.add_edge("triage", "write_tests")
        g.add_edge("write_tests", "code")
        g.add_edge("code", "verify")
        g.add_conditional_edges("verify", lambda f: f["route"], ["debug", "design_review", "review"])
        g.add_edge("debug", "verify")
        g.add_conditional_edges("design_review", lambda f: f["route"], ["verify", "review"])
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
            limit = 8 + 2 * settings.max_debug_rounds + 3 * settings.design_review_rounds + 4
            self.graph().invoke({}, {"recursion_limit": limit})
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


def new_run(requirement: str, mode: str = "build", project_id: Optional[str] = None, ask_questions: bool = False) -> RunState:
    return RunState(id=uuid.uuid4().hex[:12], mode=mode, requirement=requirement.strip(), project_id=project_id,
                    ask_questions=ask_questions and mode == "build")


def run_sync(state: RunState, sink: Optional[EventSink] = None, log: Optional[Callable[[str], None]] = None) -> RunState:
    return Orchestrator(RunContext(state, sink, log)).run()


def mermaid() -> str:
    """The orchestration graph as Mermaid, for docs and the UI."""
    return Orchestrator(RunContext(new_run("x"))).graph().get_graph().draw_mermaid()
