"""
cli.py
------
Run CodeCrew from the terminal.

    python cli.py "a function that converts roman numerals"
    python cli.py --iterate <project-id> "also support lowercase input"
"""

import argparse
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from codecrew import orchestrator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CodeCrew multi-agent software team")
    parser.add_argument("request", nargs="*", help="what to build (or change, with --iterate)")
    parser.add_argument("--iterate", metavar="PROJECT_ID", help="apply a change request to an existing project")
    args = parser.parse_args()

    request = " ".join(args.request).strip() or input("Describe what you want built: ").strip()
    if not request:
        print("You didn't type anything.")
        return 1

    mode = "iterate" if args.iterate else "build"
    state = orchestrator.new_run(request, mode=mode, project_id=args.iterate)
    state = orchestrator.run_sync(state, log=print)

    print("\n" + "=" * 60)
    if state.status == "error":
        print(f"ERROR: {state.error}")
        return 2
    v = state.verification
    print(f"Project : {state.project_id}  ({state.status})")
    print(f"Result  : {v.summary if v else 'not verified'}")
    if v and not v.passed:
        print("Remaining issues:")
        for i in v.issues:
            if i.severity == "error":
                print(f"  - [{i.source}] {i.test_id or i.file or ''}: {i.message.splitlines()[0][:140]}")
    print(f"Saved to: {state.project_dir}")
    print(f"LLM calls: {state.usage.calls}, tokens in/out: {state.usage.input_tokens}/{state.usage.output_tokens}")
    return 0 if state.status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
