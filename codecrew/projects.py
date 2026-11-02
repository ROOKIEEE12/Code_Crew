"""Generated projects on disk.

generated_projects/<project-id>/
    <source files>, tests/..., README.md
    .codecrew/project.json   spec, last verification, run history
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Optional

from codecrew.config import settings
from codecrew.schemas import Spec, Verification
from codecrew.textio import UnsafePathError, safe_relpath
from codecrew.verify import is_test_path

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
META_DIR = ".codecrew"


class ProjectNotFound(LookupError):
    pass


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    return slug[:60] or "project"


def project_path(project_id: str) -> Path:
    if not _ID.match(project_id or ""):
        raise ProjectNotFound(project_id)
    path = (settings.output_dir / project_id).resolve()
    if path.parent != settings.output_dir.resolve():
        raise ProjectNotFound(project_id)
    return path


def new_project_id(name: str) -> str:
    return f"{slugify(name)}-{time.strftime('%Y%m%d-%H%M%S')}"


def save(project_id: str, spec: Spec, files: dict[str, str], tests: dict[str, str], readme: str,
         verification: Optional[Verification], run_id: str, requirement: str) -> Path:
    root = project_path(project_id)
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in {**files, **tests}.items():
        target = root / safe_relpath(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    if readme:
        (root / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    if any(p.endswith(".py") for p in tests) and "pytest.ini" not in files:
        # Lets `python -m pytest` import project modules exactly as the sandbox did.
        (root / "pytest.ini").write_text("[pytest]\npythonpath = . src\n", encoding="utf-8")

    meta_path = root / META_DIR / "project.json"
    meta_path.parent.mkdir(exist_ok=True)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"history": []}
    meta.update(
        id=project_id,
        name=spec.project_name,
        spec=spec.model_dump(),
        verification=verification.model_dump() if verification else None,
        verification_stale=False,
        updated_at=time.time(),
    )
    meta.setdefault("created_at", time.time())
    meta["history"].append({"run_id": run_id, "requirement": requirement, "at": time.time(),
                            "passed": bool(verification and verification.passed)})
    meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return root


def load(project_id: str) -> dict:
    root = project_path(project_id)
    if not root.is_dir():
        raise ProjectNotFound(project_id)
    meta_path = root / META_DIR / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    files: dict[str, str] = {}
    tests: dict[str, str] = {}
    readme = ""
    for p in sorted(root.rglob("*")):
        if not p.is_file() or META_DIR in p.relative_to(root).parts:
            continue
        rel = p.relative_to(root).as_posix()
        try:
            rel = safe_relpath(rel)
            content = p.read_text(encoding="utf-8")
        except (UnsafePathError, UnicodeDecodeError):
            continue
        if rel == "README.md":
            readme = content
        elif is_test_path(rel):
            tests[rel] = content
        else:
            files[rel] = content
    return {
        "id": project_id,
        "name": meta.get("name", project_id),
        "spec": Spec.model_validate(meta["spec"]) if meta.get("spec") else None,
        "verification": meta.get("verification"),
        "verification_stale": bool(meta.get("verification_stale")),
        "history": meta.get("history", []),
        "created_at": meta.get("created_at", root.stat().st_ctime),
        "updated_at": meta.get("updated_at", root.stat().st_mtime),
        "files": files,
        "tests": tests,
        "readme": readme,
    }


def list_all() -> list[dict]:
    out = []
    if not settings.output_dir.exists():
        return out
    for d in settings.output_dir.iterdir():
        if not d.is_dir() or not _ID.match(d.name):
            continue
        meta_path = d / META_DIR / "project.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
        verification = meta.get("verification") or {}
        out.append({
            "id": d.name,
            "name": meta.get("name", d.name),
            "summary": (meta.get("spec") or {}).get("summary", ""),
            "passed": verification.get("passed"),
            "verification_stale": bool(meta.get("verification_stale")),
            "tests_total": verification.get("tests_total"),
            "tests_passed": verification.get("tests_passed"),
            "legacy": not meta,
            "file_count": sum(1 for p in d.rglob("*") if p.is_file() and META_DIR not in p.relative_to(d).parts),
            "created_at": meta.get("created_at", d.stat().st_ctime),
            "updated_at": meta.get("updated_at", d.stat().st_mtime),
        })
    out.sort(key=lambda x: x["updated_at"], reverse=True)
    return out


def _update_meta(root: Path, **changes) -> None:
    meta_path = root / META_DIR / "project.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.update(changes, updated_at=time.time())
    meta_path.parent.mkdir(exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")


def rename(project_id: str, name: str) -> None:
    """Changes the display name; the project id (folder) stays the same."""
    root = project_path(project_id)
    if not root.is_dir():
        raise ProjectNotFound(project_id)
    _update_meta(root, name=name)


def write_file(project_id: str, rel: str, content: str) -> None:
    """Saves a hand edit to an existing file. The last verification no longer
    describes the code, so it is marked stale until the next run."""
    root = project_path(project_id)
    rel = safe_relpath(rel)
    target = root / rel
    if not root.is_dir() or META_DIR in Path(rel).parts or not target.is_file():
        raise ProjectNotFound(rel)
    target.write_text(content, encoding="utf-8", newline="\n")
    _update_meta(root, verification_stale=True)


def _clear_readonly(func, path, _exc_info) -> None:
    """rmtree error hook: Windows refuses to delete read-only files and folders
    (OneDrive often marks synced folders read-only), so clear the flag and retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def delete(project_id: str) -> None:
    root = project_path(project_id)
    if not root.is_dir():
        raise ProjectNotFound(project_id)
    for attempt in range(5):
        try:
            shutil.rmtree(root, onerror=_clear_readonly)
            return
        except PermissionError:
            # Still locked by another program (OneDrive syncing, Explorer, an editor). Wait briefly.
            if attempt == 4:
                raise
            time.sleep(0.4 * (attempt + 1))
