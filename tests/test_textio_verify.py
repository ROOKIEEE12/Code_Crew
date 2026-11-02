import pytest

from codecrew.textio import UnsafePathError, parse_file_blocks, safe_relpath
from codecrew.verify import verify


@pytest.mark.parametrize("bad", ["../x.py", "a/../../x.py", "/etc/x.py", "C:/x.py", ".env", "a/.git/x.py", "x.exe", "con.py", ""])
def test_unsafe_paths_rejected(bad):
    with pytest.raises(UnsafePathError):
        safe_relpath(bad)


def test_safe_paths_normalised():
    assert safe_relpath("src\\app.py") == "src/app.py"
    assert safe_relpath("./a/b.js") == "a/b.js"


def test_file_blocks_strip_fences_and_reject_traversal():
    text = 'intro\n<<<FILE path="a.py">>>\n```python\nx = 1\n```\n<<<END FILE>>>'
    assert parse_file_blocks(text) == {"a.py": "x = 1\n"}
    with pytest.raises(UnsafePathError):
        parse_file_blocks('<<<FILE path="../a.py">>>\nx\n<<<END FILE>>>')
    with pytest.raises(ValueError):
        parse_file_blocks("no blocks here")


def test_verifier_catches_cross_file_and_test_failures():
    files = {
        "calc.py": "def add(a, b):\n    return a + b\n",
        "main.py": "from calc import add, mul\nimport requests\n",
        "tests/test_calc.py": "from calc import add\n\ndef test_add():\n    assert add(2, 2) == 5\n",
        "index.html": '<html><body><div id="a"></div><script src="app.js"></script><link rel="stylesheet" href="x.css"></body></html>',
        "app.js": "document.addEventListener('DOMContentLoaded', () => { document.getElementById('b'); });\n",
    }
    v = verify(files)
    messages = "\n".join(i.message for i in v.issues)
    assert not v.passed
    assert "'mul' is imported from 'calc'" in messages
    assert "import 'requests'" in messages
    assert "'x.css'" in messages
    assert "element id 'b'" in messages
    assert v.tests_total == 1 and v.tests_passed == 0
    assert any(i.test_id == "tests/test_calc.py::test_add" for i in v.issues)


def test_verifier_passes_clean_project():
    files = {
        "calc.py": "def add(a, b):\n    return a + b\n",
        "tests/test_calc.py": "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    }
    v = verify(files)
    assert v.passed, v.issues
    assert v.level == "tested" and v.tests_passed == 1


_LOCKED_TESTS = ("from calc import add\n\n"
                 "def test_ok():\n    assert add(1, 1) == 2\n\n"
                 "def test_wrong():\n    assert add(2, 2) == 5\n")


def test_skip_from_source_code_does_not_pass():
    """Source code that skips a failing locked test must not turn the run green."""
    files = {
        "calc.py": "import pytest\n\ndef add(a, b):\n    if (a, b) == (2, 2):\n        pytest.skip('unsupported')\n    return a + b\n",
        "tests/test_calc.py": _LOCKED_TESTS,
    }
    v = verify(files)
    assert not v.passed
    assert any(i.test_id == "tests/test_calc.py::test_wrong" for i in v.issues)


# Runs at interpreter start-up: writes an all-green report and exits before any test runs.
_FAKE_REPORT = ("import os, glob\n"
                "if not glob.glob('junit-js-*.xml'):\n"
                "    open('junit-python.xml', 'w').write('<testsuite><testcase classname=\"tests.test_calc\" name=\"test_ok\"/>'\n"
                "        '<testcase classname=\"tests.test_calc\" name=\"test_wrong\"/></testsuite>')\n"
                "    os._exit(0)\n")

_HIJACKS = {
    "root conftest": {"conftest.py": (
        "import pytest\n\n@pytest.hookimpl(hookwrapper=True)\n"
        "def pytest_runtest_makereport(item, call):\n    outcome = yield\n    outcome.get_result().outcome = 'passed'\n")},
    "sitecustomize": {"sitecustomize.py": _FAKE_REPORT},
    "shadowed pytest": {"src/pytest.py": _FAKE_REPORT},
    "pytest.ini addopts": {"pytest.ini": "[pytest]\naddopts = --deselect tests/test_calc.py::test_wrong\n"},
    "pyproject addopts": {"pyproject.toml": "[tool.pytest.ini_options]\naddopts = \"-k test_ok\"\n"},
}


@pytest.mark.parametrize("name", list(_HIJACKS))
def test_source_files_cannot_change_how_locked_tests_run(name):
    files = {"calc.py": "def add(a, b):\n    return a + b\n", "tests/test_calc.py": _LOCKED_TESTS, **_HIJACKS[name]}
    v = verify(files)
    assert not v.passed, f"{name} made a failing suite pass"


def test_test_authors_own_conftest_still_works():
    files = {
        "calc.py": "def add(a, b):\n    return a + b\n",
        "tests/conftest.py": "import pytest\n\n@pytest.fixture\ndef two():\n    return 2\n",
        "tests/test_calc.py": "from calc import add\n\ndef test_add(two):\n    assert add(two, two) == 4\n",
    }
    v = verify(files)
    assert v.passed, v.issues
    assert v.tests_passed == 1


def test_sandbox_hides_secrets(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    files = {
        "leak.py": "import os\n\ndef key():\n    return os.environ.get('OPENROUTER_API_KEY')\n",
        "tests/test_leak.py": "from leak import key\n\ndef test_no_key():\n    assert key() is None\n",
    }
    assert verify(files).passed


def test_docker_sandbox_uses_the_configured_image(monkeypatch, tmp_path):
    from codecrew import sandbox
    from codecrew.config import settings

    seen = {}

    def fake_run(cmd, **_):
        seen["cmd"] = cmd
        raise FileNotFoundError("docker")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    monkeypatch.setattr(sandbox, "settings", type(settings)(sandbox="docker", docker_image="my-sandbox:2"))
    sandbox.run(["python", "x.py"], tmp_path)
    assert "my-sandbox:2" in seen["cmd"]
    assert type(settings)().docker_image == "codecrew-sandbox"  # the image sandbox/Dockerfile builds
