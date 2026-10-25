"""Starts the FastAPI backend (:8000) and the Next.js frontend (:3000) together.

    python scripts/dev.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    if not (ROOT / "web" / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=ROOT / "web", check=True)
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, env=env),
        subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "web", env=env),
    ]
    print("CodeCrew API  http://127.0.0.1:8000/docs\nCodeCrew UI   http://localhost:3000  (Ctrl+C to stop)")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait()


if __name__ == "__main__":
    main()
