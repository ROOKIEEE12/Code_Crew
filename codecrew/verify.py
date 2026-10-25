"""Deterministic verification of a generated project.

Nothing in this module asks an LLM for an opinion. Each check either runs a
real tool or performs an exact structural comparison, and anything that
could not be checked is reported as "unchecked" rather than "passed".

  1. syntax     - ast / node --check / json / tag balance / brace balance
  2. contracts  - HTML asset links, JS DOM ids, Python imports & names
  3. spec       - every planned file and function actually exists
  4. lint       - ruff (pyflakes rules) and bandit (security)
  5. tests      - pytest / node:test in the sandbox, parsed from JUnit XML
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
from typing import Optional

from codecrew import sandbox
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


def run_python_tests(root: Path, files: dict[str, str]) -> Optional[TestRun]:
    tests = [p for p in files if p.endswith(".py") and is_test_path(p) and posixpath.basename(p).startswith("test_")]
    if not tests:
        return None
    xml = root / "junit-python.xml"
    res = sandbox.run(
        [*sandbox.python_cmd(), "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider",
         f"--junitxml={xml.name}", "-o", "junit_family=xunit1"],
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

def verify(files: dict[str, str], spec: Optional[Spec] = None, run_tests: bool = True) -> Verification:
    v = Verification()
    with sandbox.workspace(files) as root:
        for path, code in files.items():
            v.syntax[path] = check_syntax(path, code, root)
        for path, check in v.syntax.items():
            if check.status == "failed":
                v.issues.append(Issue(source="syntax", severity="error", file=path, message=check.output))
        v.issues += check_web_contracts(files)
        v.issues += check_python_imports(files)
        v.issues += check_spec(spec, files)
        v.issues += run_lint(root, files)
        if run_tests:
            for run in (run_python_tests(root, files), run_js_tests(root, files)):
                if run:
                    v.test_runs.append(run)

    for run in v.test_runs:
        if run.collection_error or not run.ran:
            v.issues.append(Issue(source="test", severity="error",
                                  message=f"{run.runner} could not run the test suite cleanly:\n{run.output[-2500:]}"))
        for c in run.cases:
            if c.outcome in ("failed", "error"):
                v.issues.append(Issue(source="test", severity="error", file=c.file, test_id=c.id,
                                      message=f"{c.message}\n{c.details}".strip()[-3000:]))

    cases = [c for r in v.test_runs for c in r.cases if c.outcome != "skipped"]
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
