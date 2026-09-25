"""
cli.py
------
The simplest possible way to try CodeCrew — no browser needed.
Run: python cli.py
"""

import sys
from orchestrator import run_pipeline

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    print("=== CodeCrew: Multi-Agent Software Engineering Team ===")
    request = input("Describe what you want built: ").strip()

    if not request:
        print("You didn't type anything — try again.")
        return

    print()
    result = run_pipeline(request)

    print("\n" + "=" * 60)
    print(f"PROJECT: {result['plan']['project_name']}  ({result['plan']['project_type']})")
    print("=" * 60)
    print(result["plan"]["summary"])

    print(f"\nFiles ({len(result['files'])}):")
    for path in result["files"]:
        print(f"  - {path}")

    status = "ALL CHECKS PASSED ✅" if result["tests_passed"] else "SOME ISSUES REMAIN ⚠️ (best attempt saved)"
    print(f"\nStatus: {status}")
    print(f"Saved to: {result['project_dir']}")


if __name__ == "__main__":
    main()
