"""Evaluate CodeCrew against a single-agent baseline on hidden tests.

    python -m eval.run --check                     # prove hidden tests pass on reference solutions
    python -m eval.run                             # all tasks, both modes
    python -m eval.run --tasks roman,lru --modes codecrew

baseline: one LLM call (same provider/model chain as CodeCrew's coder)
          given the requirement, with no planning, tests or debugging.
codecrew: the full multi-agent pipeline.

Both are graded only by hidden tests neither system has seen.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import time
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from codecrew import llm, orchestrator, sandbox  # noqa: E402
from codecrew.context import RunContext  # noqa: E402
from codecrew.textio import FILE_BLOCK_INSTRUCTIONS, parse_file_blocks  # noqa: E402
from codecrew.verify import is_test_path, run_python_tests  # noqa: E402
from eval.tasks import TASKS  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"

BASELINE_SYSTEM = f"""You are a senior software engineer. Implement the user's
requirement completely and correctly in Python using only the standard library.

{FILE_BLOCK_INSTRUCTIONS}"""


def grade(files: dict[str, str], hidden_tests: str) -> tuple[int, int, str]:
    source = {p: c for p, c in files.items() if not is_test_path(p)}
    with sandbox.workspace({**source, "tests/test_hidden.py": textwrap.dedent(hidden_tests)}) as root:
        run = run_python_tests(root, {"tests/test_hidden.py": ""})
    if not run or not run.ran:
        return 0, 1, (run.output if run else "no tests ran")[-1500:]
    cases = [c for c in run.cases if c.outcome != "skipped"]
    passed = sum(1 for c in cases if c.outcome == "passed")
    total = max(len(cases), 1)
    return passed, total, "" if passed == total and not run.collection_error else run.output[-1500:]


def reference_files(task: dict) -> dict[str, str]:
    ref = task["reference"]
    if isinstance(ref, dict):
        return {p: textwrap.dedent(c) for p, c in ref.items()}
    module = next(m for m in re.findall(r"^from ([\w.]+) import", task["hidden_tests"], re.MULTILINE)
                  if m.split(".")[0] not in sys.stdlib_module_names)
    return {module.replace(".", "/") + ".py": textwrap.dedent(ref)}


def run_baseline(task: dict) -> dict:
    state = orchestrator.new_run(task["requirement"])
    ctx = RunContext(state)
    t0 = time.time()
    try:
        files = llm.call_text(ctx, "coder", BASELINE_SYSTEM, task["requirement"], parse_file_blocks)
        error = None
    except Exception as e:
        files, error = {}, f"{type(e).__name__}: {e}"
    return {"files": files, "seconds": time.time() - t0, "usage": state.usage, "error": error,
            "debug_rounds": 0, "self_verified": None}


def run_codecrew(task: dict) -> dict:
    t0 = time.time()
    state = orchestrator.run_sync(orchestrator.new_run(task["requirement"]))
    return {"files": state.files, "seconds": time.time() - t0, "usage": state.usage,
            "error": state.error, "debug_rounds": len(state.debug_rounds),
            "self_verified": bool(state.verification and state.verification.passed)}


def check() -> int:
    bad = 0
    for task in TASKS:
        passed, total, out = grade(reference_files(task), task["hidden_tests"])
        ok = passed == total and not out
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {task['id']}: {passed}/{total}" + ("" if ok else f"\n{out}"))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--modes", default="baseline,codecrew")
    args = ap.parse_args()
    if args.check:
        return check()

    wanted = {t for t in args.tasks.split(",") if t}
    tasks = [t for t in TASKS if not wanted or t["id"] in wanted]
    modes = [m for m in args.modes.split(",") if m in ("baseline", "codecrew")]
    rows = []
    started = time.time()
    for task in tasks:
        for mode in modes:
            print(f"[{mode}] {task['id']} ...", flush=True)
            out = run_baseline(task) if mode == "baseline" else run_codecrew(task)
            passed, total, log = grade(out["files"], task["hidden_tests"]) if out["files"] else (0, 1, out["error"] or "")
            row = {
                "task": task["id"], "mode": mode, "solved": passed == total and not log,
                "hidden_passed": passed, "hidden_total": total, "seconds": round(out["seconds"], 1),
                "llm_calls": out["usage"].calls, "input_tokens": out["usage"].input_tokens,
                "output_tokens": out["usage"].output_tokens, "debug_rounds": out["debug_rounds"],
                "self_verified": out["self_verified"], "error": out["error"], "log": log[-800:],
            }
            rows.append(row)
            print(f"    solved={row['solved']} hidden={passed}/{total} calls={row['llm_calls']} {row['seconds']}s", flush=True)

    summary = {}
    for mode in modes:
        r = [x for x in rows if x["mode"] == mode]
        if not r:
            continue
        summary[mode] = {
            "tasks": len(r),
            "solved": sum(x["solved"] for x in r),
            "solve_rate": round(sum(x["solved"] for x in r) / len(r), 3),
            "hidden_test_pass_rate": round(sum(x["hidden_passed"] for x in r) / max(1, sum(x["hidden_total"] for x in r)), 3),
            "avg_seconds": round(sum(x["seconds"] for x in r) / len(r), 1),
            "avg_llm_calls": round(sum(x["llm_calls"] for x in r) / len(r), 1),
            "avg_output_tokens": round(sum(x["output_tokens"] for x in r) / len(r)),
        }
        if mode == "codecrew":
            claimed = [x for x in r if x["self_verified"]]
            summary[mode]["self_verified_and_solved"] = sum(x["solved"] for x in claimed)
            summary[mode]["self_verified"] = len(claimed)

    RESULTS_DIR.mkdir(exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S")
    result = {"name": name, "started_at": started, "finished_at": time.time(),
              "providers": llm.provider_status()["order"], "summary": summary, "rows": rows}
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(f"Saved eval/results/{name}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
