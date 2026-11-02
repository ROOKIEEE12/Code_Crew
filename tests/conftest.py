"""Shared test setup."""

import pytest

from codecrew.config import settings


@pytest.fixture(autouse=True)
def _isolated(tmp_path):
    """Every test saves projects in its own temp folder (never the real generated_projects)
    and skips the slow headless-browser checks; tests that want them turn them back on."""
    output_dir = settings.output_dir
    object.__setattr__(settings, "output_dir", tmp_path / "generated_projects")
    if "testserver" not in settings.allowed_hosts:  # the host name FastAPI's TestClient uses
        object.__setattr__(settings, "allowed_hosts", [*settings.allowed_hosts, "testserver"])
    object.__setattr__(settings, "browser_checks", "off")
    yield
    object.__setattr__(settings, "output_dir", output_dir)
    object.__setattr__(settings, "browser_checks", "auto")
