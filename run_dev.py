"""
run_dev.py
----------
Launches both FastAPI backend and Vite frontend development server concurrently.
Usage:
    python run_dev.py
"""

import subprocess
import sys
import os
import time

def start_dev():
    print("=" * 60)
    print("🚀 Starting CodeCrew Full Stack Development Environment")
    print("=" * 60)

    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    python_exe = os.path.join(root_dir, "venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable

    print(f"Backend Server:  http://127.0.0.1:8000 (FastAPI)")
    print(f"Frontend Studio: http://localhost:5173 (React + Vite)")
    print(f"Production Host: http://127.0.0.1:8000/ (FastAPI serves built React)")
    print("-" * 60)

    # Start FastAPI
    backend_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=root_dir,
    )

    # Start Vite Frontend
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down CodeCrew development servers...")
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_proc.wait()
        frontend_proc.wait()
        print("Done.")

if __name__ == "__main__":
    start_dev()
