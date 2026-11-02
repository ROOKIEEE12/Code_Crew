"""Headless browser (Playwright + Chromium), used for three things:

  - opening a generated web page to catch JavaScript errors and layout
    problems the static checks cannot see (verify.py),
  - screenshots of the page for the design review,
  - screenshots of a reference website the user linked to.

Everything here is optional: if Playwright or its browser is missing,
`available()` is False and callers skip these steps and say so.

Generated pages run in Chromium's sandbox. Network access is limited to
https requests to public hosts (web fonts, CDNs); anything aimed at this
machine or a private network is blocked.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from codecrew import sandbox
from codecrew.config import settings

DESKTOP = (1280, 800)
PHONE = (390, 844)
_MAX_SHOT_HEIGHT = {DESKTOP: 3600, PHONE: 2600}

_lock = threading.Lock()
_available: Optional[bool] = None
_unavailable_reason = ""
_host_ok: dict[str, bool] = {}


def available() -> bool:
    """True when Playwright and Chromium are installed (checked once)."""
    global _available, _unavailable_reason
    if settings.browser_checks == "off":
        _unavailable_reason = "turned off (BROWSER_CHECKS=off)"
        return False
    with _lock:
        if _available is None:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    p.chromium.launch().close()
                _available = True
            except Exception as e:  # not installed, or the browser was never downloaded
                _available = False
                _unavailable_reason = (
                    "Playwright is not installed (pip install playwright && python -m playwright install chromium)"
                    if isinstance(e, ImportError) else f"the browser could not start ({type(e).__name__})"
                )
        return _available


def unavailable_reason() -> str:
    return _unavailable_reason


def public_host(host: str) -> bool:
    """True only if every address the host resolves to is on the public internet."""
    if not host:
        return False
    if host in _host_ok:
        return _host_ok[host]
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
        ok = bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)
    except (OSError, ValueError):
        ok = False
    _host_ok[host] = ok
    return ok


def _allowed(url: str, local_root: Optional[Path]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in ("data", "blob", "about"):
        return True
    if parsed.scheme == "file":  # only the project's own files
        if local_root is None:
            return False
        target = Path(url2pathname(unquote(parsed.path))).resolve()
        return target == local_root.resolve() or local_root.resolve() in target.parents
    return parsed.scheme == "https" and public_host(parsed.hostname or "")


@contextmanager
def _page(viewport: tuple[int, int], local_root: Optional[Path] = None) -> Iterator:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=1,
                reduced_motion="reduce",  # reveal-on-scroll content shows without animating
                service_workers="block",
            )
            context.route("**/*", lambda route: route.continue_() if _allowed(route.request.url, local_root) else route.abort())
            yield context.new_page()
        finally:
            browser.close()


def _settle(page) -> None:
    """Scrolls through the page so lazy and reveal-on-scroll content renders, then back to the top."""
    try:
        height = page.evaluate("document.documentElement.scrollHeight")
        step = page.viewport_size["height"]
        for y in range(0, min(height, 12000), step):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(80)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)
    except Exception:
        pass  # a page that breaks while scrolling still gets its screenshot


def _shot(page, viewport: tuple[int, int]) -> bytes:
    height = page.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
    height = max(viewport[1], min(int(height or viewport[1]), _MAX_SHOT_HEIGHT[viewport]))
    return page.screenshot(type="jpeg", quality=70, full_page=True,
                           clip={"x": 0, "y": 0, "width": viewport[0], "height": height})


# ---------------------------------------------------------------- generated projects

@dataclass
class PageReport:
    page: str
    page_errors: list[str] = field(default_factory=list)      # uncaught exceptions
    console_errors: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)    # local files the page asked for that do not exist
    phone_overflow_px: int = 0                                # how far the page scrolls sideways on a phone
    hidden_sections: list[str] = field(default_factory=list)  # design sections that exist but take no space
    screenshots: dict[str, bytes] = field(default_factory=dict)  # "desktop" / "phone" -> JPEG


def check_pages(files: dict[str, str], pages: list[str], sections: dict[str, list[str]] | None = None,
                screenshots: bool = False) -> list[PageReport]:
    """Opens each HTML page of the project at desktop and phone size."""
    reports = []
    with sandbox.workspace(files) as root:
        for page_path in pages:
            report = PageReport(page_path)
            url = (root / page_path).resolve().as_uri()
            for label, viewport in (("desktop", DESKTOP), ("phone", PHONE)):
                with _page(viewport, root) as page:
                    if label == "desktop":
                        page.on("pageerror", lambda e, r=report: r.page_errors.append(str(e)[:400]))
                        page.on("console", lambda m, r=report: m.type == "error" and r.console_errors.append(m.text[:400]))
                        page.on("requestfailed", lambda req, r=report: req.url.startswith("file:")
                                and r.missing_files.append(req.url.rsplit("/", 1)[-1]))
                    try:
                        page.goto(url, wait_until="load", timeout=15000)
                    except Exception as e:
                        report.page_errors.append(f"The page did not finish loading: {type(e).__name__}")
                        continue
                    _settle(page)
                    if label == "phone":
                        report.phone_overflow_px = int(page.evaluate(
                            "Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"))
                    else:
                        for sid in (sections or {}).get(page_path, []):
                            size = page.evaluate(
                                "id => { const el = document.getElementById(id); if (!el) return -1;"
                                " const r = el.getBoundingClientRect(); return r.width * r.height; }", sid)
                            if size == 0:
                                report.hidden_sections.append(sid)
                    if screenshots:
                        report.screenshots[label] = _shot(page, viewport)
            reports.append(report)
    return reports


# ---------------------------------------------------------------- reference websites

def capture_url(url: str) -> tuple[str, bytes]:
    """Renders a public web page (JavaScript included); returns (HTML, desktop screenshot)."""
    with _page(DESKTOP) as page:
        page.goto(url, wait_until="load", timeout=25000)
        _settle(page)
        return page.content(), _shot(page, DESKTOP)
