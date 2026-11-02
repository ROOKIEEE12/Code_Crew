"""Reference reader: when a request contains links ("make it like
https://..."), read those pages and hand the agents what they contain:
page outline, navigation, calls to action, text, colours and fonts, plus a
screenshot when the headless browser is available.

Without this the agents only ever see the URL as text and have to guess.
A site that blocks automated readers is reported to the user plainly, so
the run never pretends to have followed a page it could not open.

Only public http(s) addresses are fetched; hosts on this machine or a
private network are refused.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

from codecrew import render
from codecrew.schemas import Reference

MAX_LINKS = 3
_MAX_BYTES = 2_000_000
_MAX_CSS_BYTES = 400_000
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
_LANDMARKS = {"header", "nav", "main", "section", "footer", "article", "aside", "form"}
_BLOCKED = {401: "it needs a login", 403: "the site blocks automated readers", 429: "the site is rate-limiting readers",
            503: "the site blocks automated readers or is down"}


def find_urls(text: str) -> list[str]:
    out: list[str] = []
    for m in _URL.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?)]}")
        if url not in out:
            out.append(url)
    return out[:MAX_LINKS]


# ---------------------------------------------------------------- HTML digest

class _Digest(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title = ""
        self.meta: dict[str, str] = {}
        self.outline: list[str] = []
        self.nav: list[str] = []
        self.ctas: list[str] = []
        self.text: list[str] = []
        self.css: list[str] = []
        self.stylesheets: list[str] = []
        self.font_links: list[str] = []
        self.images = 0
        self._capture: Optional[str] = None  # tag whose text is being collected
        self._buf: list[str] = []
        self._in_nav = 0
        self._in_title = False
        self._attrs: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in _SKIP:
            self.skip += 1
            if tag == "style":
                self._capture = "style"
                self._buf = []
            return
        if self.skip:
            return
        if a.get("style"):
            self.css.append(a["style"])
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key in ("description", "og:title", "og:description", "theme-color"):
                self.meta[key] = a.get("content", "")[:300]
        elif tag == "link":
            rel = a.get("rel", "").lower()
            href = a.get("href", "")
            if "stylesheet" in rel and href:
                (self.font_links if "fonts.googleapis.com" in href else self.stylesheets).append(href)
        elif tag == "img":
            self.images += 1
        elif tag == "nav":
            self._in_nav += 1
        if tag in _LANDMARKS and tag != "form":
            label = a.get("aria-label") or a.get("id") or ""
            if tag in ("header", "nav", "footer") or label:
                self.outline.append(f"[{tag}{' ' + label if label else ''}]")
        if tag in ("h1", "h2", "h3", "a", "button") and self._capture is None:
            self._capture = tag
            self._buf = []
            self._attrs = a

    def handle_endtag(self, tag):
        if tag in _SKIP:
            if tag == "style" and self._capture == "style":
                self.css.append("".join(self._buf))
                self._capture = None
            self.skip = max(0, self.skip - 1)
            return
        if tag == "title":
            self._in_title = False
        elif tag == "nav":
            self._in_nav = max(0, self._in_nav - 1)
        if tag == self._capture:
            text = " ".join("".join(self._buf).split())[:120]
            self._capture = None
            if not text:
                return
            if tag in ("h1", "h2", "h3"):
                self.outline.append(f"{tag.upper()}: {text}")
            elif tag == "a" and self._in_nav:
                self.nav.append(text)
            elif tag == "button" or re.search(r"btn|button|cta", self._attrs.get("class", ""), re.IGNORECASE):
                self.ctas.append(text)

    def handle_data(self, data):
        if self._capture == "style":
            self._buf.append(data)
            return
        if self.skip:
            return
        if self._in_title:
            self.title += data
        if self._capture:
            self._buf.append(data)
        chunk = " ".join(data.split())
        if len(chunk) > 2:
            self.text.append(chunk)


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: list[str] = []
    for i in items:
        if i not in seen:
            seen.append(i)
    return seen[:limit]


_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")
_FONT = re.compile(r"font-family\s*:\s*([^;}{]+)", re.IGNORECASE)
_GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "inherit", "initial", "ui-sans-serif",
                  "-apple-system", "blinkmacsystemfont", "cursive", "emoji", "ui-monospace", "var"}


def _colors(css: str) -> list[str]:
    found: Counter[str] = Counter()
    for m in _HEX.finditer(css):
        h = m.group(1).lower()
        found["#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)] += 1
    for m in _RGB.finditer(css):
        r, g, b = (min(255, int(x)) for x in m.groups())
        found[f"#{r:02x}{g:02x}{b:02x}"] += 1
    return [c for c, _ in found.most_common(10)]


def _fonts(css: str, font_links: list[str]) -> list[str]:
    found: Counter[str] = Counter()
    for href in font_links:
        for fam in parse_qs(urlparse(href).query).get("family", []):
            found[fam.split(":")[0].replace("+", " ")] += 5
    for m in _FONT.finditer(css):
        first = m.group(1).split(",")[0].strip().strip("'\"")
        if first and first.lower() not in _GENERIC_FONTS and not first.startswith("var("):
            found[first] += 1
    return [f for f, _ in found.most_common(4)]


# ---------------------------------------------------------------- fetching

def _fetch(client, url: str, limit: int) -> tuple[int, str, str]:
    """GET following redirects by hand so every hop is checked; returns (status, content type, text)."""
    for _ in range(6):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not render.public_host(parsed.hostname or ""):
            raise ValueError("only public web addresses can be read")
        with client.stream("GET", url) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            body = b""
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > limit:
                    break
            return r.status_code, r.headers.get("content-type", ""), body.decode(r.encoding or "utf-8", errors="replace")
    raise ValueError("too many redirects")


def read(url: str, with_browser: bool = True) -> tuple[Reference, Optional[bytes]]:
    """Reads one reference page; returns what it contains and, if possible, a screenshot."""
    import httpx

    ref = Reference(url=url, ok=False)
    html, problem, shot = "", "", None
    try:
        with httpx.Client(timeout=15, headers={"User-Agent": _UA, "Accept-Language": "en"}, follow_redirects=False) as client:
            status, ctype, body = _fetch(client, url, _MAX_BYTES)
            if status >= 400:
                problem = f"HTTP {status}: {_BLOCKED.get(status, 'the page could not be loaded')}"
            elif "html" not in ctype.lower():
                problem = f"it is not a web page ({ctype.split(';')[0] or 'unknown type'})"
            else:
                html = body
            digest = _digest(html) if html else None
            # Pages built with JavaScript have little text in their HTML; a real browser sees more.
            thin = digest is not None and len(" ".join(digest.text)) < 300
            if with_browser and render.available() and (html or problem.startswith("HTTP")):
                try:
                    rendered, shot = render.capture_url(url)
                    if _bot_check(_digest(rendered)):
                        shot = None  # a screenshot of a "checking your browser" page would mislead
                        if not html:
                            problem += "; the browser was shown a bot check instead of the page"
                    elif thin or not html:
                        html, problem = rendered, ""
                        digest = _digest(html)
                except Exception as e:
                    if not html:
                        problem += f"; the browser could not open it either ({type(e).__name__})"
            if digest and html and _bot_check(digest):
                problem, html = "the site shows a bot check (e.g. Cloudflare) instead of the page", ""
            if digest and html:
                css = "\n".join(digest.css)
                for href in digest.stylesheets[:3]:
                    try:
                        s, t, text = _fetch(client, urljoin(url, href), _MAX_CSS_BYTES)
                        if s < 400 and "css" in t:
                            css += "\n" + text
                    except (ValueError, httpx.HTTPError):
                        continue
                ref.ok = True
                ref.title = " ".join((digest.meta.get("og:title") or digest.title).split())[:200]
                ref.description = digest.meta.get("description") or digest.meta.get("og:description", "")
                ref.outline = _dedupe(digest.outline, 40)
                if digest.nav:
                    ref.outline.insert(0, "Navigation: " + " · ".join(_dedupe(digest.nav, 10)))
                if digest.ctas:
                    ref.outline.append("Buttons / calls to action: " + " · ".join(_dedupe(digest.ctas, 8)))
                if digest.images:
                    ref.outline.append(f"{digest.images} image(s) on the page")
                ref.colors = _colors(css)
                if digest.meta.get("theme-color"):
                    ref.colors.insert(0, digest.meta["theme-color"])
                ref.fonts = _fonts(css, digest.font_links)
                ref.excerpt = " ".join(_dedupe(digest.text, 400))[:2500]
    except ValueError as e:
        problem = str(e)
    except httpx.HTTPError as e:
        problem = f"the site could not be reached ({type(e).__name__})"
    if not ref.ok:
        ref.error = problem or "nothing readable was found on the page"
    return ref, shot


_BOT_CHECK = re.compile(r"just a moment|attention required|checking your browser|verify you are human|"
                        r"access denied|are you a robot|captcha|enable javascript and cookies", re.IGNORECASE)


def _bot_check(d: _Digest) -> bool:
    """True for interstitial pages (Cloudflare and similar) shown to automated readers."""
    return bool(_BOT_CHECK.search(d.title)) or (len(" ".join(d.text)) < 400 and bool(_BOT_CHECK.search(" ".join(d.text))))


def _digest(html: str) -> _Digest:
    d = _Digest()
    try:
        d.feed(html)
        d.close()
    except Exception:  # malformed markup: keep whatever was parsed
        pass
    return d


# ---------------------------------------------------------------- prompt text

def brief(refs: list[Reference]) -> str:
    """What the references contain, written for the Planner and the Coder."""
    if not refs:
        return ""
    parts = ["Reference material the user pointed to. Match its layout, section order, visual style and tone "
             "closely, but write original copy about the user's own project: never reuse the reference's "
             "headlines, slogans, brand names or product claims."]
    for r in refs:
        if not r.ok:
            parts.append(f"\nReference {r.url}: could NOT be read ({r.error}). Do not guess what it contains; "
                         "follow the user's words and any images instead, and say so in the assumptions.")
            continue
        lines = [f"\nReference {r.url}"]
        if r.title:
            lines.append(f"Title: {r.title}")
        if r.description:
            lines.append(f"Description: {r.description}")
        if r.outline:
            lines.append("Page outline, top to bottom:\n" + "\n".join(f"- {o}" for o in r.outline))
        if r.colors:
            lines.append("Colours used most: " + ", ".join(r.colors))
        if r.fonts:
            lines.append("Fonts: " + ", ".join(r.fonts))
        if r.excerpt:
            lines.append(f"Text on the page (excerpt): {r.excerpt}")
        parts.append("\n".join(lines))
    return "\n".join(parts)
