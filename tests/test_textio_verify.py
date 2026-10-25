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


def test_sandbox_hides_secrets(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    files = {
        "leak.py": "import os\n\ndef key():\n    return os.environ.get('OPENROUTER_API_KEY')\n",
        "tests/test_leak.py": "from leak import key\n\ndef test_no_key():\n    assert key() is None\n",
    }
    assert verify(files).passed
