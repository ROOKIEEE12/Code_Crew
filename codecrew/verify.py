"""Deterministic verification of a generated project.

Nothing in this module asks an LLM for an opinion. Each check either runs a
real tool or performs an exact structural comparison, and anything that
could not be checked is reported as "unchecked" rather than "passed".

  1. syntax     - ast / node --check / json / tag balance / brace balance
  2. contracts  - HTML asset links, JS DOM ids, Python imports & names
  3. spec       - every planned file and function actually exists
  4. quality    - web pages: viewport, placeholder text, every section of the
                  design brief, palette use, responsive CSS
  5. browser    - web pages opened in headless Chromium at desktop and phone
                  size: JavaScript errors on load, sideways scrolling, empty
                  sections (only when Playwright is installed)
  6. lint       - ruff (pyflakes rules) and bandit (security)
  7. tests      - pytest / node:test in the sandbox, parsed from JUnit XML
"""

from __future__ import annotations

import ast
import json
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

from codecrew import render, sandbox
from codecrew.schemas import FileCheck, Issue, Spec, TestCaseResult, TestRun, Verification
from codecrew.textio import language_for

# ---------------------------------------------------------------- helpers

_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr", "!doctype"}
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|\{|\$)", re.IGNORECASE)


def is_test_path(path: str) -> bool:
    name = posixpath.basename(path)
    return (
        path.startswith("tests/")
        or name.startswith("test_")
        or name.endswith("_test.py")
        or re.search(r"\.test\.(?:c|m)?js$", name) is not None
    )


class _HTMLScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.refs: list[tuple[str, str, int]] = []  # (attr value, tag, line)
        self.stack: list[tuple[str, int]] = []
        self.problems: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        line = self.getpos()[0]
        if tag == "script" and a.get("src"):
            self.refs.append((a["src"], tag, line))
        elif tag == "link" and a.get("href") and "stylesheet" in (a.get("rel") or ""):
            self.refs.append((a["href"], tag, line))
        elif tag in ("img", "source") and a.get("src"):
            self.refs.append((a["src"], tag, line))
        elif tag == "a" and a.get("href"):
            self.refs.append((a["href"], tag, line))
        if tag not in _VOID_TAGS:
            self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for unclosed, ln in self.stack[i + 1 :]:
                    if unclosed not in ("p", "li", "td", "th", "tr", "option", "dt", "dd"):
                        self.problems.append((ln, f"<{unclosed}> is never closed"))
                del self.stack[i:]
                return
        self.problems.append((self.getpos()[0], f"stray closing tag </{tag}>"))


def _scan_html(code: str) -> _HTMLScan:
    scan = _HTMLScan()
    scan.feed(code)
    scan.close()
    return scan


# ---------------------------------------------------------------- 1. syntax

def check_syntax(path: str, code: str, root: Path) -> FileCheck:
    lang = language_for(path)
    if lang == "python":
        try:
            ast.parse(code, filename=path)
            return FileCheck(status="passed", tool="python-ast")
        except SyntaxError as e:
            return FileCheck(status="failed", tool="python-ast", output=f"line {e.lineno}: {e.msg}")
    if lang == "javascript":
        node = sandbox.node_path()
        if not node:
            return FileCheck(status="unchecked", tool="node", output="Node.js not installed.")
        res = subprocess.run(
            [node, "--check", str(root / path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20
        )
        if res.returncode == 0:
            return FileCheck(status="passed", tool="node --check")
        return FileCheck(status="failed", tool="node --check", output=res.stderr.replace(str(root), "").strip()[-1500:])
    if lang == "json":
        try:
            json.loads(code)
            return FileCheck(status="passed", tool="json")
        except json.JSONDecodeError as e:
            return FileCheck(status="failed", tool="json", output=str(e))
    if lang == "html":
        problems = _scan_html(code).problems
        if problems:
            return FileCheck(status="failed", tool="tag-balance", output="\n".join(f"line {ln}: {m}" for ln, m in problems[:10]))
        return FileCheck(status="passed", tool="tag-balance")
    if lang == "css":
        stripped = re.sub(r"/\*[\s\S]*?\*/", "", code)
        depth = 0
        for ch in stripped:
            depth += (ch == "{") - (ch == "}")
            if depth < 0:
                break
        if depth != 0:
            return FileCheck(status="failed", tool="brace-balance", output="Unbalanced { } braces.")
        return FileCheck(status="passed", tool="brace-balance")
    return FileCheck(status="unchecked", tool="none", output=f"No checker for {lang}.")


# ---------------------------------------------------------------- 2. contracts

def _resolve_ref(from_path: str, ref: str) -> Optional[str]:
    ref = ref.split("#")[0].split("?")[0].strip()
    if not ref or _EXTERNAL.match(ref):
        return None
    base = posixpath.dirname(from_path)
    return posixpath.normpath(posixpath.join(base, ref.lstrip("/") if ref.startswith("/") else ref))


def check_web_contracts(files: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    html_ids: set[str] = set()
    html_files = {p: c for p, c in files.items() if language_for(p) == "html"}
    for path, code in html_files.items():
        scan = _scan_html(code)
        html_ids |= scan.ids
        for ref, tag, line in scan.refs:
            target = _resolve_ref(path, ref)
            if target and target not in files and not (tag == "a" and target.endswith("/")):
                issues.append(Issue(source="contract", severity="error", file=path, line=line,
                                    message=f"<{tag}> references '{ref}' but no such file exists in the project."))

    if not html_files:
        return issues

    js_files = {p: c for p, c in files.items() if language_for(p) == "javascript" and not is_test_path(p)}
    all_js = "\n".join(js_files.values())
    id_lookup = re.compile(r"""getElementById\(\s*['"]([\w-]+)['"]\s*\)|querySelector(?:All)?\(\s*['"]#([\w-]+)['"]\s*\)""")
    for path, code in js_files.items():
        for lineno, line in enumerate(code.splitlines(), 1):
            for m in id_lookup.finditer(line):
                el_id = m.group(1) or m.group(2)
                if el_id in html_ids:
                    continue
                created = re.search(rf"""\bid\s*[=:]\s*['"`]{re.escape(el_id)}['"`]|id=\\?['"]{re.escape(el_id)}\\?['"]""", all_js)
                if not created:
                    issues.append(Issue(source="contract", severity="error", file=path, line=lineno,
                                        message=f"Looks up element id '{el_id}', which no HTML file defines and no script creates."))
    return issues


# ---------------------------------------------------------------- 3b. web quality

_PLACEHOLDER = re.compile(
    r"lorem ipsum|dolor sit amet|placeholder text|your (?:text|content|title|tagline) here|\bTODO\b|\bTBD\b|"
    r"\b(?:feature|service|product|item) (?:one|two|three|[123])\b|example\.com", re.IGNORECASE)


class _VisibleText(HTMLParser):
    """Text a visitor would read, with line numbers (scripts and styles excluded)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.chunks: list[tuple[int, str]] = []
        self.imgs_without_alt: list[int] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.skip += 1
        elif tag == "img" and "alt" not in dict(attrs):
            self.imgs_without_alt.append(self.getpos()[0])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.chunks.append((self.getpos()[0], data.strip()))


def _hex6(value: str) -> str:
    h = value.strip().lower().lstrip("#")
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h[:6])


def web_pages(files: dict[str, str]) -> list[str]:
    return sorted(p for p in files if language_for(p) == "html" and not is_test_path(p))


def check_web_quality(files: dict[str, str], spec: Optional[Spec]) -> list[Issue]:
    """Deterministic checks that a web page is complete and usable, beyond "it parses"."""
    pages = web_pages(files)
    if not pages:
        return []
    issues: list[Issue] = []
    design = spec.design if spec else None
    # With a design brief these are part of the plan, so missing them is a defect.
    ux = "error" if design else "warning"
    css = "\n".join(c for p, c in files.items() if p.endswith(".css"))
    css += "\n".join(m for code in (files[p] for p in pages) for m in re.findall(r"<style[^>]*>([\s\S]*?)</style>", code, re.IGNORECASE))

    for path in pages:
        code = files[path]
        low = code.lower()
        if not re.search(r"<meta[^>]+name\s*=\s*[\"']?viewport", low):
            issues.append(Issue(source="quality", severity=ux, file=path, message=(
                'Missing <meta name="viewport" content="width=device-width, initial-scale=1">, '
                "so phones show a tiny zoomed-out desktop page.")))
        if not re.search(r"<title>\s*[^<\s]", low):
            issues.append(Issue(source="quality", severity="warning", file=path, message="The page has no <title>."))
        if not re.search(r"<html[^>]*\slang\s*=", low):
            issues.append(Issue(source="quality", severity="warning", file=path, message='<html> has no lang attribute (e.g. lang="en").'))
        text = _VisibleText()
        try:
            text.feed(code)
        except Exception:
            continue
        for line in text.imgs_without_alt[:3]:
            issues.append(Issue(source="quality", severity="warning", file=path, line=line,
                                message="<img> has no alt text for screen readers."))
        for line, chunk in text.chunks:
            m = _PLACEHOLDER.search(chunk)
            if m:
                issues.append(Issue(source="quality", severity="error", file=path, line=line, message=(
                    f"Placeholder text '{m.group(0)}' is visible on the page. Write real content for this project.")))
                break

    if design:
        ids = {p: _scan_html(files[p]).ids for p in pages}
        for sec in design.sections:
            page = sec.page if sec.page in ids else (pages[0] if len(pages) == 1 else sec.page)
            if page not in ids:
                issues.append(Issue(source="quality", severity="error", file=sec.page, message=(
                    f"Design section '{sec.name}' belongs on {sec.page}, which does not exist.")))
            elif sec.id not in ids[page]:
                issues.append(Issue(source="quality", severity="error", file=page, message=(
                    f'Design section \'{sec.name}\' is missing: no element with id="{sec.id}" in {page}. '
                    f"It should show: {sec.content[:200]}")))
        planned = {_hex6(c.hex) for c in design.palette if re.fullmatch(r"#?[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", c.hex.strip())}
        css_low = css.lower()
        short = {h: "#" + h[1] + h[3] + h[5] for h in planned if h[1] == h[2] and h[3] == h[4] and h[5] == h[6]}
        used = {h for h in planned if h in css_low or (h in short and re.search(re.escape(short[h]) + r"\b", css_low))}
        if len(planned) >= 3 and len(used) * 2 < len(planned):
            issues.append(Issue(source="quality", severity="warning", message=(
                f"The CSS uses only {len(used)} of the {len(planned)} planned colours "
                f"(missing: {', '.join(sorted(planned - used))}).")))

    if css.strip() or design:
        if not re.search(r"@media|clamp\(|minmax\(|auto-fit|auto-fill|@container", css, re.IGNORECASE):
            issues.append(Issue(source="quality", severity=ux, message=(
                "There is no responsive CSS (no @media, clamp() or auto-fit grid), so the layout will not adapt to phones.")))
        if design and not re.search(r":hover|:focus", css):
            issues.append(Issue(source="quality", severity="warning", message="No :hover or :focus styles: links and buttons give no feedback."))
        declarations = css.count(";")
        if design and declarations < 60:
            issues.append(Issue(source="quality", severity="warning", message=(
                f"Very little styling ({declarations} CSS declarations) for a designed page.")))
    return issues


def browser_issues(files: dict[str, str], spec: Optional[Spec]) -> list[Issue]:
    """Opens each page in headless Chromium; only call when render.available()."""
    pages = web_pages(files)[:5]
    design = spec.design if spec else None
    sections: dict[str, list[str]] = {}
    for sec in design.sections if design else []:
        page = sec.page if sec.page in pages else (pages[0] if len(pages) == 1 else sec.page)
        sections.setdefault(page, []).append(sec.id)
    issues: list[Issue] = []
    for r in render.check_pages({p: c for p, c in files.items() if not is_test_path(p)}, pages, sections):
        for err in r.page_errors[:3]:
            issues.append(Issue(source="runtime", severity="error", file=r.page, message=(
                f"JavaScript error in the browser when {r.page} loads: {err}")))
        for err in [e for e in r.console_errors if "Failed to load resource" not in e][:3]:
            issues.append(Issue(source="runtime", severity="warning", file=r.page, message=f"Browser console error: {err}"))
        for name in sorted(set(r.missing_files))[:3]:
            issues.append(Issue(source="runtime", severity="error", file=r.page, message=(
                f"In the browser, {r.page} asked for '{name}', which does not exist.")))
        if r.phone_overflow_px > 40:
            issues.append(Issue(source="quality", severity="error" if design else "warning", file=r.page, message=(
                f"On a 390px-wide phone the page is {r.phone_overflow_px}px wider than the screen and scrolls sideways. "
                "Find the element with a fixed width or long unbroken content and make it fit.")))
        for sid in r.hidden_sections:
            issues.append(Issue(source="quality", severity="warning", file=r.page, message=(
                f'Section id="{sid}" exists but takes up no space on the page (empty or hidden).')))
    return issues


def _module_map(files: dict[str, str]) -> dict[str, str]:
    modules: dict[str, str] = {}
    for path in files:
        if not path.endswith(".py"):
            continue
        mod = path[:-3].replace("/", ".")
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        modules[mod] = path
        if mod.startswith("src."):
            modules[mod[4:]] = path
    # Directories that contain modules act as (namespace) packages.
    for mod in list(modules):
        parts = mod.split(".")
        for i in range(1, len(parts)):
            modules.setdefault(".".join(parts[:i]), "")
    return modules


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.If, ast.Try)):
            sub = ast.Module(body=list(ast.iter_child_nodes(node)), type_ignores=[])
            sub.body = [n for n in sub.body if isinstance(n, ast.stmt)]
            names |= _top_level_names(sub)
    return names


def _requirements(files: dict[str, str]) -> set[str]:
    reqs = set()
    for line in files.get("requirements.txt", "").splitlines():
        name = re.split(r"[<>=!~\[; ]", line.strip(), maxsplit=1)[0]
        if name and not name.startswith("#"):
            reqs.add(name.lower().replace("-", "_"))
    return reqs


# Import names that differ from their PyPI distribution names.
_IMPORT_ALIASES = {"yaml": "pyyaml", "bs4": "beautifulsoup4", "PIL": "pillow", "sklearn": "scikit_learn", "cv2": "opencv_python"}


def check_python_imports(files: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    modules = _module_map(files)
    reqs = _requirements(files)
    stdlib = set(sys.stdlib_module_names)
    trees: dict[str, ast.Module] = {}
    for path, code in files.items():
        if path.endswith(".py"):
            try:
                trees[path] = ast.parse(code)
            except SyntaxError:
                pass

    for path in trees:
        top = path.split("/")[0].removesuffix(".py")
        if top in stdlib and not is_test_path(path):
            issues.append(Issue(source="contract", severity="error", file=path,
                                message=f"'{path}' shadows the standard-library module '{top}'; rename it."))

    def third_party_ok(top: str) -> bool:
        key = top.lower().replace("-", "_")
        return top in stdlib or key in reqs or _IMPORT_ALIASES.get(top, "").lower() in reqs or top in ("pytest",)

    for path, tree in trees.items():
        testing = is_test_path(path)
        pkg = path[:-3].replace("/", ".").rsplit(".", 1)[0] if "/" in path else ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if alias.name not in modules and top not in modules and not third_party_ok(top):
                        issues.append(Issue(source="contract", severity="error", file=path, line=node.lineno,
                                            message=f"import '{alias.name}' is not part of the project, the standard library, or requirements.txt."))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = pkg.split(".") if pkg else []
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    mod = ".".join([*base, node.module] if node.module else base)
                else:
                    mod = node.module or ""
                top = mod.split(".")[0]
                if mod in modules:
                    target = modules[mod]
                    if not target or target not in trees:
                        continue
                    defined = _top_level_names(trees[target])
                    for alias in node.names:
                        if alias.name == "*" or alias.name in defined or f"{mod}.{alias.name}" in modules:
                            continue
                        issues.append(Issue(source="contract", severity="error", file=path, line=node.lineno,
                                            message=f"'{alias.name}' is imported from '{mod}' ({target}) but is not defined there."))
                elif node.level or top in modules:
                    issues.append(Issue(source="contract", severity="error", file=path, line=node.lineno,
                                        message=f"Module '{mod}' does not exist in the project."))
                elif not third_party_ok(top) and not testing:
                    issues.append(Issue(source="contract", severity="error", file=path, line=node.lineno,
                                        message=f"import from '{mod}' is not part of the project, the standard library, or requirements.txt."))
    return issues


# ---------------------------------------------------------------- 3. spec

def check_spec(spec: Optional[Spec], files: dict[str, str]) -> list[Issue]:
    if not spec:
        return []
    issues: list[Issue] = []
    for fs in spec.files:
        if fs.path not in files:
            issues.append(Issue(source="spec", severity="error", file=fs.path, message="Planned file was not generated."))
            continue
        code = files[fs.path]
        lang = language_for(fs.path)
        defined: set[str] = set()
        if lang == "python":
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue
            defined = _top_level_names(tree)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    defined |= {f"{node.name}.{n.name}" for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        elif lang == "javascript":
            defined = set(re.findall(r"(?:function\s*\*?\s*|class\s+|(?:const|let|var)\s+)([A-Za-z_$][\w$]*)", code))
            defined |= set(re.findall(r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", code, re.MULTILINE))
        else:
            continue
        for fn in fs.functions:
            name = fn.name.strip()
            short = name.split(".")[-1]
            if name not in defined and short not in defined:
                issues.append(Issue(source="spec", severity="error", file=fs.path,
                                    message=f"Spec requires '{name}' ({fn.signature}) but it is not defined in this file."))
    return issues


# ---------------------------------------------------------------- 4. lint

_RUFF_ERRORS = re.compile(r"^(E9|F63|F7|F82)")


def run_lint(root: Path, files: dict[str, str]) -> list[Issue]:
    py = [p for p in files if p.endswith(".py")]
    if not py:
        return []
    issues: list[Issue] = []
    res = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--output-format", "json",
         "--select", "E9,F", "--ignore", "F401,F541,F841", *py],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    try:
        for d in json.loads(res.stdout or "[]"):
            rel = Path(d["filename"]).resolve().relative_to(root.resolve()).as_posix()
            sev = "error" if _RUFF_ERRORS.match(d.get("code") or "") else "warning"
            issues.append(Issue(source="lint", severity=sev, file=rel, line=d["location"]["row"],
                                message=f"{d.get('code')}: {d['message']}"))
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    src = [p for p in py if not is_test_path(p)]
    if src:
        res = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", *src],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        try:
            for r in json.loads(res.stdout or "{}").get("results", []):
                sev = r.get("issue_severity")
                if sev not in ("HIGH", "MEDIUM"):
                    continue
                issues.append(Issue(
                    source="security",
                    severity="error" if sev == "HIGH" and r.get("issue_confidence") != "LOW" else "warning",
                    file=Path(r["filename"]).as_posix().lstrip("./"),
                    line=r.get("line_number"),
                    message=f"{r.get('test_id')}: {r.get('issue_text')}",
                ))
        except (json.JSONDecodeError, KeyError):
            pass
    return issues


# ---------------------------------------------------------------- 5. tests

def _relative(file: str, root: Path) -> str:
    p = Path(file)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            pass
    return p.as_posix()


def _parse_junit(xml_path: Path, default_file: str, root: Path) -> list[TestCaseResult]:
    cases: list[TestCaseResult] = []
    tree = ET.parse(xml_path).getroot()
    for tc in tree.iter("testcase"):
        name = tc.get("name", "")
        classname = tc.get("classname", "")
        file = tc.get("file") or (classname.replace(".", "/") + ".py" if classname and default_file.endswith(".py") else default_file)
        file = _relative(file, root)
        outcome, message, details = "passed", "", ""
        for tag, out in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
            el = tc.find(tag)
            if el is not None:
                outcome, message, details = out, el.get("message", ""), (el.text or "")
                break
        test_id = f"{file}::{name}" if file else name
        root_str = str(root)
        details = details.replace(root_str + "\\", "").replace(root_str + "/", "").replace(root_str, "")
        cases.append(TestCaseResult(id=test_id, file=file, name=name, outcome=outcome,
                                    message=message[:1000], details=details[-4000:]))
    return cases


# Files Python or pytest load before any test runs. Written by the Coder or Debugger
# (not the Test Author), they could change the outcome of the locked tests.
_HARNESS_FILES = {"conftest.py", "sitecustomize.py", "usercustomize.py"}
_HARNESS_MODULES = {"pytest", "_pytest", "pluggy"}
# The verifier's own pytest config: with -c, pytest ignores any pytest.ini, pyproject.toml,
# setup.cfg or tox.ini in the project, so their addopts cannot deselect or rewrite tests.
_PYTEST_INI = ".codecrew-pytest.ini"


def check_test_harness(files: dict[str, str]) -> list[Issue]:
    issues = []
    for path in files:
        if is_test_path(path):
            continue
        parts = path.split("/")
        top = parts[1] if parts[0] == "src" and len(parts) > 1 else parts[0]
        if posixpath.basename(path) in _HARNESS_FILES or posixpath.splitext(top)[0] in _HARNESS_MODULES:
            issues.append(Issue(source="contract", severity="error", file=path, message=(
                f"{path} would change how the locked tests run, which source code may not do. "
                "Remove it; shared test fixtures belong in tests/conftest.py, written by the Test Author.")))
    return issues


def run_python_tests(root: Path, files: dict[str, str]) -> Optional[TestRun]:
    tests = [p for p in files if p.endswith(".py") and is_test_path(p) and posixpath.basename(p).startswith("test_")]
    if not tests:
        return None
    xml = root / "junit-python.xml"
    (root / _PYTEST_INI).write_text("[pytest]\n", encoding="utf-8")
    res = sandbox.run(
        [*sandbox.python_cmd(), "-m", "pytest", "-c", _PYTEST_INI, "--rootdir", ".", *tests, "-q",
         "-p", "no:cacheprovider", f"--junitxml={xml.name}", "-o", "junit_family=xunit1"],
        root,
    )
    if res.timed_out or not xml.exists():
        return TestRun(runner="pytest", ran=False, output=res.output[-6000:], collection_error=True)
    cases = _parse_junit(xml, default_file=".py", root=root)
    collection_error = res.returncode in (2, 3, 4) or any(c.outcome == "error" and not c.name.startswith("test") for c in cases)
    return TestRun(runner="pytest", ran=True, cases=cases, output=res.output[-6000:], collection_error=collection_error)


def run_js_tests(root: Path, files: dict[str, str]) -> Optional[TestRun]:
    tests = [p for p in files if re.search(r"\.test\.(?:c|m)?js$", p)]
    if not tests:
        return None
    node = sandbox.node_path()
    if not node:
        return TestRun(runner="node:test", ran=False, output="Node.js not installed; JavaScript tests could not run.")
    cases: list[TestCaseResult] = []
    outputs = []
    collection_error = False
    for i, test in enumerate(tests):
        xml = root / f"junit-js-{i}.xml"
        res = sandbox.run([node, "--test", "--test-reporter=junit", f"--test-reporter-destination={xml.name}", test], root)
        outputs.append(res.output)
        if res.timed_out or not xml.exists():
            collection_error = True
            continue
        file_cases = [c for c in _parse_junit(xml, default_file=test, root=root) if c.name]
        for c in file_cases:
            if posixpath.basename(c.name.replace("\\", "/")) == posixpath.basename(test):
                c.name = "(file failed to load)"
            c.file, c.id = test, f"{test}::{c.name}"
        if res.returncode != 0 and not any(c.outcome in ("failed", "error") for c in file_cases):
            collection_error = True  # file crashed before/outside tests
        cases.extend(file_cases)
    return TestRun(runner="node:test", ran=True, cases=cases, output="\n".join(outputs)[-6000:], collection_error=collection_error)


# ---------------------------------------------------------------- orchestration

Progress = Callable[[dict], None]


def _step(progress: Optional[Progress], key: str, label: str, cmd: str):
    """Reports a check as running, and returns a function that reports its result."""
    if progress:
        progress({"key": key, "label": label, "cmd": cmd, "status": "running"})

    def done(ok: bool, result: str, output: str = "") -> None:
        if progress:
            progress({"key": key, "label": label, "cmd": cmd, "status": "ok" if ok else "bad",
                      "result": result, "output": output[-2500:]})

    return done


def _test_result(run: TestRun) -> tuple[bool, str]:
    if not run.ran or run.collection_error:
        return False, "could not run cleanly"
    passed = sum(1 for c in run.cases if c.outcome == "passed")
    skipped = sum(1 for c in run.cases if c.outcome == "skipped")
    failed = len(run.cases) - passed - skipped
    return passed == len(run.cases), (f"{passed} passed" + (f" · {failed} failed" if failed else "")
                                      + (f" · {skipped} skipped" if skipped else ""))


def verify(files: dict[str, str], spec: Optional[Spec] = None, run_tests: bool = True,
           progress: Optional[Progress] = None, browser: bool = True) -> Verification:
    v = Verification()
    with sandbox.workspace(files) as root:
        langs = sorted({"python" if p.endswith(".py") else "node" for p in files if p.endswith((".py", ".js", ".mjs", ".cjs"))})
        done = _step(progress, "syntax", "Checked syntax", " + ".join(
            {"python": "python ast", "node": "node --check"}[x] for x in langs) or "file structure")
        for path, code in files.items():
            v.syntax[path] = check_syntax(path, code, root)
        bad_syntax = [p for p, c in v.syntax.items() if c.status == "failed"]
        for path in bad_syntax:
            v.issues.append(Issue(source="syntax", severity="error", file=path, message=v.syntax[path].output))
        checked = sum(1 for c in v.syntax.values() if c.status != "unchecked")
        done(not bad_syntax, f"{len(bad_syntax)} file(s) broken" if bad_syntax else f"{checked} file(s) ok",
             "\n\n".join(f"{p}:\n{v.syntax[p].output}" for p in bad_syntax))

        done = _step(progress, "contracts", "Checked links between files", "imports, element ids, spec signatures")
        found = check_web_contracts(files) + check_python_imports(files) + check_spec(spec, files) + check_test_harness(files)
        v.issues += found
        errs = [i for i in found if i.severity == "error"]
        done(not errs, f"{len(errs)} problem(s)" if errs else "all consistent",
             "\n".join(f"{i.file or 'project'}: {i.message.splitlines()[0]}" for i in found[:12]))

        if web_pages(files):
            done = _step(progress, "quality", "Checked the web page quality", "viewport, real content, design sections, responsive CSS")
            found = check_web_quality(files, spec)
            v.issues += found
            errs = [i for i in found if i.severity == "error"]
            done(not errs, f"{len(errs)} problem(s), {len(found) - len(errs)} note(s)" if found else "looks complete",
                 "\n".join(f"{i.file or 'project'}: {i.message}" for i in found[:12]))
            if browser and render.available():
                done = _step(progress, "browser", "Opened the page in a real browser", "chromium · desktop 1280px + phone 390px")
                try:
                    found = browser_issues(files, spec)
                except Exception as e:  # a browser hiccup is not the project's fault
                    done(True, f"skipped ({type(e).__name__})")
                else:
                    v.issues += found
                    errs = [i for i in found if i.severity == "error"]
                    done(not errs, f"{len(errs)} problem(s), {len(found) - len(errs)} note(s)" if found else "no errors, fits on phones",
                         "\n".join(f"{i.file or 'project'}: {i.message}" for i in found[:12]))

        if any(p.endswith(".py") for p in files):
            done = _step(progress, "lint", "Lint and security scan", "ruff + bandit")
            found = run_lint(root, files)
            v.issues += found
            errs = [i for i in found if i.severity == "error"]
            done(not errs, f"{len(errs)} error(s), {len(found) - len(errs)} warning(s)" if found else "clean",
                 "\n".join(f"{i.file}:{i.line} {i.message}" for i in found[:12]))

        if run_tests:
            for key, label, cmd, runner in (
                ("pytest", "Ran Python tests", "pytest -q", run_python_tests),
                ("node", "Ran JavaScript tests", "node --test", run_js_tests),
            ):
                has_tests = any(
                    (p.endswith(".py") and is_test_path(p) and posixpath.basename(p).startswith("test_")) if key == "pytest"
                    else re.search(r"\.test\.(?:c|m)?js$", p) for p in files)
                if not has_tests:
                    continue
                done = _step(progress, key, label, cmd)
                run = runner(root, files)
                if run:
                    v.test_runs.append(run)
                    ok, result = _test_result(run)
                    done(ok, result, run.output)
                else:
                    done(True, "no tests")

    for run in v.test_runs:
        if run.collection_error or not run.ran:
            v.issues.append(Issue(source="test", severity="error",
                                  message=f"{run.runner} could not run the test suite cleanly:\n{run.output[-2500:]}"))
        for c in run.cases:
            if c.outcome in ("failed", "error"):
                v.issues.append(Issue(source="test", severity="error", file=c.file, test_id=c.id,
                                      message=f"{c.message}\n{c.details}".strip()[-3000:]))
            elif c.outcome == "skipped":
                # A locked test must actually run: a skip (or xfail) never counts as a pass.
                v.issues.append(Issue(source="test", severity="error", file=c.file, test_id=c.id, message=(
                    f"The test was skipped ({c.message or 'no reason given'}). Locked tests must run; "
                    "code may not skip them, and a skip does not count as passing.")))

    cases = [c for r in v.test_runs for c in r.cases]
    v.tests_total = len(cases)
    v.tests_passed = sum(1 for c in cases if c.outcome == "passed")
    expects_tests = bool(spec and any(f.testable for f in spec.files))
    v.level = "tested" if v.tests_total else "static_only"
    if expects_tests and not v.tests_total:
        v.issues.append(Issue(source="test", severity="error", message="Spec has testable files but no tests executed."))

    errors = [i for i in v.issues if i.severity == "error"]
    v.passed = not errors
    unchecked = [p for p, c in v.syntax.items() if c.status == "unchecked"]
    v.summary = (
        f"{v.tests_passed}/{v.tests_total} tests passed; "
        f"{len(errors)} error(s), {len(v.issues) - len(errors)} warning(s)"
        + (f"; not machine-checked: {', '.join(unchecked)}" if unchecked else "")
    )
    return v
