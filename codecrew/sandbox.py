"""Isolated execution of generated code.

The project is materialised into a fresh temp directory (folder structure
preserved) and commands run with a scrubbed environment: no API keys or
other secrets from this process are visible to generated code.

SANDBOX=process (default) uses a subprocess with a timeout.
SANDBOX=docker additionally runs inside a network-less, memory-capped
container built from sandbox/Dockerfile.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from codecrew.config import settings
from codecrew.textio import safe_relpath

_PASSTHROUGH_ENV = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "LANG")


@dataclass
class ExecResult:
    returncode: int
    output: str
    timed_out: bool = False


@contextmanager
def workspace(files: dict[str, str]) -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="codecrew-"))
    try:
        for rel, content in files.items():
            target = root / safe_relpath(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _scrubbed_env(workdir: Path) -> dict[str, str]:
    env = {k: os.environ[k] for k in _PASSTHROUGH_ENV if k in os.environ}
    env.update(
        HOME=str(workdir),
        USERPROFILE=str(workdir),
        PYTHONPATH=os.pathsep.join([str(workdir), str(workdir / "src")]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        NO_COLOR="1",
    )
    return env


def run(cmd: list[str], workdir: Path, timeout: int | None = None) -> ExecResult:
    timeout = timeout or settings.test_timeout_sec
    if settings.sandbox == "docker":
        cmd = [
            "docker", "run", "--rm", "--network", "none", "--memory", "512m", "--cpus", "1",
            "--pids-limit", "256", "-v", f"{workdir}:/work", "-w", "/work",
            "-e", "PYTHONPATH=/work:/work/src", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "codecrew-sandbox", *[_container_cmd(c) for c in cmd],
        ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            env=_scrubbed_env(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return ExecResult(proc.returncode, (proc.stdout or "") + (proc.stderr or ""))
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return ExecResult(-1, partial + f"\n[sandbox] Timed out after {timeout}s (infinite loop or blocking input?).", True)
    except FileNotFoundError as e:
        return ExecResult(-1, f"[sandbox] Command not found: {e}")


def _container_cmd(part: str) -> str:
    """Host interpreter paths become the container's interpreter."""
    if part == sys.executable:
        return "python"
    return part


def python_cmd() -> list[str]:
    return [sys.executable]


def node_path() -> str | None:
    return "node" if settings.sandbox == "docker" else shutil.which("node")
