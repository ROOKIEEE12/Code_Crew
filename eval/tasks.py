"""Benchmark tasks for comparing CodeCrew against a single-agent baseline.

Each task has a requirement (what a user would type), hidden tests that
neither system sees, and a reference solution proving the hidden tests are
correct (`python -m eval.run --check`). Requirements name the module and
function signatures so hidden tests can import them.
"""

TASKS = [
    {
        "id": "roman",
        "requirement": "Create roman.py with to_roman(n: int) -> str and from_roman(s: str) -> int for 1..3999. "
                       "Raise ValueError for out-of-range numbers and for invalid or non-canonical numerals such as 'IIII' or 'IC'.",
        "reference": '''
_V = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
def to_roman(n):
    if not isinstance(n, int) or not 1 <= n <= 3999: raise ValueError(n)
    out = ""
    for v, s in _V:
        while n >= v: out += s; n -= v
    return out
def from_roman(s):
    if not isinstance(s, str) or not s: raise ValueError(s)
    vals = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
    if any(c not in vals for c in s): raise ValueError(s)
    total = 0
    for i, c in enumerate(s):
        v = vals[c]
        total += -v if i + 1 < len(s) and vals[s[i+1]] > v else v
    if not 1 <= total <= 3999 or to_roman(total) != s: raise ValueError(s)
    return total
''',
        "hidden_tests": '''
import pytest
from roman import to_roman, from_roman
def test_known(): assert to_roman(1994) == "MCMXCIV" and from_roman("MMXXIV") == 2024
def test_roundtrip():
    for n in range(1, 4000): assert from_roman(to_roman(n)) == n
@pytest.mark.parametrize("bad", [0, 4000, -5])
def test_range(bad):
    with pytest.raises(ValueError): to_roman(bad)
@pytest.mark.parametrize("bad", ["IIII", "IC", "VX", "", "ABC", "MMMM"])
def test_invalid(bad):
    with pytest.raises(ValueError): from_roman(bad)
''',
    },
    {
        "id": "brackets",
        "requirement": "Create brackets.py with is_balanced(s: str) -> bool that checks (), [] and {} are balanced and properly nested; other characters are ignored.",
        "reference": '''
def is_balanced(s):
    pairs, stack = {")":"(", "]":"[", "}":"{"}, []
    for c in s:
        if c in "([{": stack.append(c)
        elif c in pairs:
            if not stack or stack.pop() != pairs[c]: return False
    return not stack
''',
        "hidden_tests": '''
from brackets import is_balanced
def test_basic(): assert is_balanced("([]{})") and is_balanced("") and is_balanced("a(b)c")
def test_unbalanced(): assert not is_balanced("(]") and not is_balanced("((") and not is_balanced(")(") and not is_balanced("([)]")
def test_nested(): assert is_balanced("{[()()]}") and not is_balanced("{[(])}")
''',
    },
    {
        "id": "wordfreq",
        "requirement": "Create wordfreq.py with top_words(text: str, n: int) -> list[tuple[str, int]] returning the n most frequent words, "
                       "case-insensitive, where words are runs of letters and apostrophes (strip leading/trailing apostrophes). "
                       "Sort by count descending, then alphabetically. n <= 0 returns [].",
        "reference": '''
import re
from collections import Counter
def top_words(text, n):
    if n <= 0: return []
    words = [w.strip("'") for w in re.findall(r"[a-z']+", text.lower())]
    c = Counter(w for w in words if w)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
''',
        "hidden_tests": '''
from wordfreq import top_words
def test_basic(): assert top_words("the cat the dog THE cat", 2) == [("the", 3), ("cat", 2)]
def test_ties(): assert top_words("b a c b a c", 3) == [("a", 2), ("b", 2), ("c", 2)]
def test_apostrophes(): assert top_words("don't 'quoted' don't", 2) == [("don't", 2), ("quoted", 1)]
def test_edge(): assert top_words("", 3) == [] and top_words("a b", 0) == [] and top_words("a", 5) == [("a", 1)]
def test_punctuation(): assert top_words("Hi! hi, hi... 42 times", 1) == [("hi", 3)]
''',
    },
    {
        "id": "lru",
        "requirement": "Create lru.py with class LRUCache(capacity: int) providing get(key) -> value or None and put(key, value). "
                       "When full, put evicts the least recently used key; get and put both count as use. capacity < 1 raises ValueError. "
                       "len(cache) returns the number of stored items.",
        "reference": '''
from collections import OrderedDict
class LRUCache:
    def __init__(self, capacity):
        if capacity < 1: raise ValueError(capacity)
        self.capacity, self._d = capacity, OrderedDict()
    def get(self, key):
        if key not in self._d: return None
        self._d.move_to_end(key); return self._d[key]
    def put(self, key, value):
        self._d[key] = value; self._d.move_to_end(key)
        if len(self._d) > self.capacity: self._d.popitem(last=False)
    def __len__(self): return len(self._d)
''',
        "hidden_tests": '''
import pytest
from lru import LRUCache
def test_eviction():
    c = LRUCache(2); c.put(1, "a"); c.put(2, "b"); c.get(1); c.put(3, "c")
    assert c.get(2) is None and c.get(1) == "a" and c.get(3) == "c" and len(c) == 2
def test_update_counts_as_use():
    c = LRUCache(2); c.put(1, 1); c.put(2, 2); c.put(1, 10); c.put(3, 3)
    assert c.get(1) == 10 and c.get(2) is None
def test_capacity():
    with pytest.raises(ValueError): LRUCache(0)
''',
    },
    {
        "id": "intervals",
        "requirement": "Create intervals.py with merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]] that merges overlapping or touching "
                       "closed intervals and returns them sorted by start. An interval with start > end raises ValueError.",
        "reference": '''
def merge(intervals):
    for a, b in intervals:
        if a > b: raise ValueError((a, b))
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]: out[-1] = (out[-1][0], max(out[-1][1], b))
        else: out.append((a, b))
    return out
''',
        "hidden_tests": '''
import pytest
from intervals import merge
def test_merge(): assert merge([(5, 7), (1, 3), (2, 4)]) == [(1, 4), (5, 7)]
def test_touching(): assert merge([(1, 2), (2, 3)]) == [(1, 3)]
def test_contained(): assert merge([(1, 10), (2, 3)]) == [(1, 10)]
def test_empty(): assert merge([]) == []
def test_invalid():
    with pytest.raises(ValueError): merge([(3, 1)])
''',
    },
    {
        "id": "money",
        "requirement": "Create money.py with split_bill(total_cents: int, people: int) -> list[int] that splits a bill as evenly as possible in whole cents; "
                       "the first people get the extra cents, so results differ by at most 1 and sum to the total. "
                       "people < 1 or total_cents < 0 raises ValueError.",
        "reference": '''
def split_bill(total_cents, people):
    if people < 1 or total_cents < 0: raise ValueError
    q, r = divmod(total_cents, people)
    return [q + 1 if i < r else q for i in range(people)]
''',
        "hidden_tests": '''
import pytest
from money import split_bill
def test_even(): assert split_bill(900, 3) == [300, 300, 300]
def test_remainder(): assert split_bill(1000, 3) == [334, 333, 333]
def test_sum():
    for t in range(0, 200, 7):
        for p in range(1, 9):
            r = split_bill(t, p); assert sum(r) == t and max(r) - min(r) <= 1
@pytest.mark.parametrize("args", [(100, 0), (-1, 2)])
def test_invalid(args):
    with pytest.raises(ValueError): split_bill(*args)
''',
    },
    {
        "id": "csvstats",
        "requirement": "Create csvstats.py with column_stats(csv_text: str, column: str) -> dict that parses CSV text with a header row and returns "
                       "{'count', 'mean', 'min', 'max'} for the numeric values in that column, skipping empty or non-numeric cells. "
                       "Raise KeyError if the column does not exist and ValueError if it has no numeric values. Quoted fields with commas must work.",
        "reference": '''
import csv, io
def column_stats(csv_text, column):
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    reader = csv.reader(io.StringIO(csv_text)); header = next(reader, [])
    if column not in header: raise KeyError(column)
    vals = []
    for r in rows:
        try: vals.append(float(r[column]))
        except (TypeError, ValueError): pass
    if not vals: raise ValueError(column)
    return {"count": len(vals), "mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals)}
''',
        "hidden_tests": '''
import pytest
from csvstats import column_stats
DATA = 'name,price,note\\n"Smith, J",10,a\\nB,20,"x, y"\\nC,,z\\nD,abc,w\\nE,30,v\\n'
def test_stats():
    s = column_stats(DATA, "price")
    assert s["count"] == 3 and s["mean"] == pytest.approx(20) and s["min"] == 10 and s["max"] == 30
def test_missing_column():
    with pytest.raises(KeyError): column_stats(DATA, "nope")
def test_no_numbers():
    with pytest.raises(ValueError): column_stats(DATA, "note")
''',
    },
    {
        "id": "slugify",
        "requirement": "Create slug.py with slugify(text: str, max_length: int = 50) -> str: lowercase, transliterate accented Latin letters to ASCII "
                       "(e.g. 'é' -> 'e'), replace every run of non-alphanumeric characters with a single '-', strip leading/trailing '-', "
                       "and truncate to max_length without leaving a trailing '-'.",
        "reference": '''
import re, unicodedata
def slugify(text, max_length=50):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:max_length].rstrip("-")
''',
        "hidden_tests": '''
from slug import slugify
def test_basic(): assert slugify("Hello, World!") == "hello-world"
def test_accents(): assert slugify("Café Déjà Vu") == "cafe-deja-vu"
def test_runs(): assert slugify("  a -- b __ c  ") == "a-b-c"
def test_truncate(): assert slugify("abc def ghi", max_length=8) == "abc-def"
def test_empty(): assert slugify("!!!") == ""
''',
    },
    {
        "id": "dates",
        "requirement": "Create workdays.py with add_business_days(start: datetime.date, days: int, holidays: set[datetime.date] = frozenset()) -> datetime.date "
                       "that moves forward (or backward for negative days) skipping Saturdays, Sundays and holidays. days == 0 returns start unchanged.",
        "reference": '''
import datetime
def add_business_days(start, days, holidays=frozenset()):
    step = 1 if days >= 0 else -1
    d, left = start, abs(days)
    while left:
        d += datetime.timedelta(days=step)
        if d.weekday() < 5 and d not in holidays: left -= 1
    return d
''',
        "hidden_tests": '''
from datetime import date
from workdays import add_business_days
def test_skip_weekend(): assert add_business_days(date(2026, 10, 9), 1) == date(2026, 10, 12)
def test_holiday(): assert add_business_days(date(2026, 10, 9), 1, {date(2026, 10, 12)}) == date(2026, 10, 13)
def test_backward(): assert add_business_days(date(2026, 10, 12), -1) == date(2026, 10, 9)
def test_zero(): assert add_business_days(date(2026, 10, 10), 0) == date(2026, 10, 10)
def test_many(): assert add_business_days(date(2026, 10, 5), 10) == date(2026, 10, 19)
''',
    },
    {
        "id": "inventory",
        "requirement": "Create inventory.py with class Inventory: add(sku: str, qty: int), remove(sku: str, qty: int), quantity(sku) -> int (0 if unknown), "
                       "and low_stock(threshold: int) -> list[str] of skus with quantity below threshold, sorted. qty must be a positive int else ValueError; "
                       "removing more than available raises ValueError and leaves stock unchanged. A sku whose quantity reaches 0 is removed entirely.",
        "reference": '''
class Inventory:
    def __init__(self): self._s = {}
    def _check(self, qty):
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0: raise ValueError(qty)
    def add(self, sku, qty): self._check(qty); self._s[sku] = self._s.get(sku, 0) + qty
    def remove(self, sku, qty):
        self._check(qty)
        if self._s.get(sku, 0) < qty: raise ValueError(sku)
        self._s[sku] -= qty
        if self._s[sku] == 0: del self._s[sku]
    def quantity(self, sku): return self._s.get(sku, 0)
    def low_stock(self, threshold): return sorted(k for k, v in self._s.items() if v < threshold)
''',
        "hidden_tests": '''
import pytest
from inventory import Inventory
def test_flow():
    inv = Inventory(); inv.add("b", 5); inv.add("a", 2); inv.remove("b", 4)
    assert inv.quantity("b") == 1 and inv.low_stock(3) == ["a", "b"]
def test_over_remove():
    inv = Inventory(); inv.add("a", 1)
    with pytest.raises(ValueError): inv.remove("a", 2)
    assert inv.quantity("a") == 1
def test_zero_removed():
    inv = Inventory(); inv.add("a", 1); inv.remove("a", 1)
    assert inv.quantity("a") == 0 and inv.low_stock(100) == []
@pytest.mark.parametrize("q", [0, -1, 1.5])
def test_bad_qty(q):
    with pytest.raises(ValueError): Inventory().add("a", q)
''',
    },
    {
        "id": "matrix",
        "requirement": "Create spiral.py with spiral_order(matrix: list[list[int]]) -> list[int] returning elements in clockwise spiral order "
                       "starting top-left. Works for empty and non-square matrices.",
        "reference": '''
def spiral_order(matrix):
    out, m = [], [row[:] for row in matrix]
    while m and m[0]:
        out += m.pop(0)
        m = [list(r) for r in zip(*m)][::-1] if m and m[0] else []
    return out
''',
        "hidden_tests": '''
from spiral import spiral_order
def test_square(): assert spiral_order([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]
def test_rect(): assert spiral_order([[1,2,3,4],[5,6,7,8],[9,10,11,12]]) == [1,2,3,4,8,12,11,10,9,5,6,7]
def test_column(): assert spiral_order([[1],[2],[3]]) == [1,2,3]
def test_empty(): assert spiral_order([]) == [] and spiral_order([[]]) == []
''',
    },
    {
        "id": "passwords",
        "requirement": "Create password_check.py with check_password(pw: str) -> list[str] returning the list of failed rule codes in this order: "
                       "'length' (fewer than 12 characters), 'upper' (no uppercase letter), 'lower' (no lowercase), 'digit' (no digit), "
                       "'symbol' (no character that is not a letter, digit or whitespace), 'space' (contains whitespace). An empty list means valid.",
        "reference": '''
def check_password(pw):
    fails = []
    if len(pw) < 12: fails.append("length")
    if not any(c.isupper() for c in pw): fails.append("upper")
    if not any(c.islower() for c in pw): fails.append("lower")
    if not any(c.isdigit() for c in pw): fails.append("digit")
    if not any(not c.isalnum() and not c.isspace() for c in pw): fails.append("symbol")
    if any(c.isspace() for c in pw): fails.append("space")
    return fails
''',
        "hidden_tests": '''
from password_check import check_password
def test_valid(): assert check_password("Correct-Horse9") == []
def test_all_fail(): assert check_password(" ") == ["length", "upper", "lower", "digit", "symbol", "space"]
def test_order(): assert check_password("abcdefghijk1!") == ["upper"]
def test_space(): assert check_password("Abcdefgh 12!x") == ["space"]
''',
    },
    {
        "id": "tokenizer",
        "requirement": "Create calc.py with evaluate(expr: str) -> float that evaluates arithmetic with + - * /, parentheses, unary minus and decimal numbers, "
                       "using normal precedence and left associativity. Do not use eval(). Raise ValueError for malformed input and ZeroDivisionError for division by zero.",
        "reference": '''
import re
def evaluate(expr):
    toks = re.findall(r"\\d+\\.\\d*|\\.\\d+|\\d+|[-+*/()]|\\S", expr)
    pos = 0
    def peek(): return toks[pos] if pos < len(toks) else None
    def take():
        nonlocal pos; t = peek(); pos += 1; return t
    def expr_():
        v = term()
        while peek() in ("+", "-"): v = v + term() if take() == "+" else v - term()
        return v
    def term():
        v = factor()
        while peek() in ("*", "/"):
            op = take(); r = factor()
            if op == "*": v *= r
            else:
                if r == 0: raise ZeroDivisionError
                v /= r
        return v
    def factor():
        t = take()
        if t == "-": return -factor()
        if t == "+": return factor()
        if t == "(":
            v = expr_()
            if take() != ")": raise ValueError("missing )")
            return v
        try: return float(t)
        except (TypeError, ValueError): raise ValueError(t)
    if not toks: raise ValueError("empty")
    v = expr_()
    if pos != len(toks): raise ValueError("trailing")
    return v
''',
        "hidden_tests": '''
import pytest
from calc import evaluate
def test_precedence(): assert evaluate("2 + 3 * 4") == 14
def test_parens(): assert evaluate("(2 + 3) * 4") == 20
def test_assoc(): assert evaluate("8 - 3 - 2") == 3 and evaluate("16 / 4 / 2") == 2
def test_unary(): assert evaluate("-3 + -(2 * -2)") == 1
def test_decimal(): assert evaluate("1.5 * 2") == pytest.approx(3.0)
@pytest.mark.parametrize("bad", ["", "2 +", "(1 + 2", "1 + 2)", "2 $ 3"])
def test_malformed(bad):
    with pytest.raises(ValueError): evaluate(bad)
def test_zero():
    with pytest.raises(ZeroDivisionError): evaluate("1 / (2 - 2)")
''',
    },
    {
        "id": "ratelimit",
        "requirement": "Create ratelimit.py with class TokenBucket(capacity: int, refill_per_sec: float, clock=time.monotonic) and allow(cost: int = 1) -> bool. "
                       "The bucket starts full, refills continuously up to capacity, and allow consumes tokens only when enough are available. "
                       "The clock argument is a zero-argument callable returning seconds, so tests can control time.",
        "reference": '''
import time
class TokenBucket:
    def __init__(self, capacity, refill_per_sec, clock=time.monotonic):
        self.capacity, self.rate, self.clock = capacity, refill_per_sec, clock
        self.tokens, self.last = float(capacity), clock()
    def allow(self, cost=1):
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= cost:
            self.tokens -= cost; return True
        return False
''',
        "hidden_tests": '''
from ratelimit import TokenBucket
class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
def test_burst_then_block():
    c = Clock(); b = TokenBucket(3, 1.0, clock=c)
    assert [b.allow() for _ in range(4)] == [True, True, True, False]
def test_refill():
    c = Clock(); b = TokenBucket(2, 2.0, clock=c)
    b.allow(); b.allow(); assert not b.allow()
    c.t = 0.5; assert b.allow() and not b.allow()
def test_cap():
    c = Clock(); b = TokenBucket(2, 10.0, clock=c); c.t = 100
    assert b.allow(2) and not b.allow()
def test_cost_not_consumed_on_reject():
    c = Clock(); b = TokenBucket(3, 1.0, clock=c)
    assert not b.allow(4) and b.allow(3)
''',
    },
    {
        "id": "multifile",
        "requirement": "Build a small task-tracker library as a package: tasks/models.py with a dataclass Task(id: int, title: str, done: bool = False, tags: list[str]), "
                       "tasks/store.py with class TaskStore providing add(title: str, tags: list[str] | None = None) -> Task (ids start at 1 and increase), "
                       "complete(task_id: int) -> Task (KeyError if unknown), by_tag(tag: str) -> list[Task] (in id order), "
                       "and to_json() -> str / TaskStore.from_json(s: str) -> TaskStore round-tripping all tasks and continuing id numbering. "
                       "Empty or whitespace-only titles raise ValueError.",
        "reference": {
            "tasks/__init__.py": "",
            "tasks/models.py": '''
from dataclasses import dataclass, field
@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    tags: list = field(default_factory=list)
''',
            "tasks/store.py": '''
import json
from dataclasses import asdict
from tasks.models import Task
class TaskStore:
    def __init__(self): self._t, self._next = {}, 1
    def add(self, title, tags=None):
        if not title or not title.strip(): raise ValueError(title)
        t = Task(self._next, title, False, list(tags or [])); self._t[t.id] = t; self._next += 1; return t
    def complete(self, task_id):
        if task_id not in self._t: raise KeyError(task_id)
        self._t[task_id].done = True; return self._t[task_id]
    def by_tag(self, tag): return [t for _, t in sorted(self._t.items()) if tag in t.tags]
    def to_json(self): return json.dumps({"next": self._next, "tasks": [asdict(t) for t in self._t.values()]})
    @classmethod
    def from_json(cls, s):
        d = json.loads(s); st = cls(); st._next = d["next"]
        for t in d["tasks"]: st._t[t["id"]] = Task(**t)
        return st
''',
        },
        "hidden_tests": '''
import pytest
from tasks.store import TaskStore
from tasks.models import Task
def test_add_and_ids():
    s = TaskStore(); a = s.add("a", ["x"]); b = s.add("b")
    assert (a.id, b.id) == (1, 2) and isinstance(a, Task) and b.tags == []
def test_complete_and_tags():
    s = TaskStore(); s.add("a", ["x"]); s.add("b", ["y"]); s.add("c", ["x"])
    assert s.complete(1).done and [t.id for t in s.by_tag("x")] == [1, 3]
    with pytest.raises(KeyError): s.complete(99)
def test_roundtrip():
    s = TaskStore(); s.add("a", ["x"]); s.complete(1)
    s2 = TaskStore.from_json(s.to_json())
    assert s2.by_tag("x")[0].done and s2.add("b").id == 2
def test_blank_title():
    with pytest.raises(ValueError): TaskStore().add("   ")
''',
    },
]
